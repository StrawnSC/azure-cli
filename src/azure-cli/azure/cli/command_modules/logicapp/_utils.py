# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import time
import datetime
import uuid
import json
import re
import sys
import ssl
from urllib.parse import urlparse
from urllib.request import urlopen
from knack.log import get_logger
from msrestazure.tools import parse_resource_id, is_valid_resource_id
from msrestazure.azure_exceptions import CloudError
from azure.mgmt.applicationinsights import ApplicationInsightsManagementClient
from azure.mgmt.storage import StorageManagementClient

from azure.cli.core.commands import LongRunningOperation
from azure.cli.core.commands.client_factory import get_mgmt_service_client
from azure.cli.core.profiles import ResourceType, get_sdk
from azure.cli.core.azclierror import (ResourceNotFoundError, UnclassifiedUserFault, AzureInternalError,
                                       MutuallyExclusiveArgumentError, CLIError, RequiredArgumentMissingError,
                                       ValidationError)
from azure.cli.core.util import get_az_user_agent, shell_safe_json_parse, get_json_object, in_cloud_console

from ._client_factory import web_client_factory, ex_handler_factory
from ._constants import APPSETTINGS_TO_MASK, CONTAINER_APPSETTING_NAMES, MULTI_CONTAINER_TYPES
from ._validators import validate_range_of_int_flag, validate_and_convert_to_int


logger = get_logger(__name__)


# TODO consider breaking this up into different util files

def generic_site_operation(cli_ctx, resource_group_name, name, operation_name, slot=None,
                           extra_parameter=None, client=None, api_version=None):
    # api_version was added to support targeting a specific API
    # Based on get_appconfig_service_client example
    client = client or web_client_factory(cli_ctx, api_version=api_version)
    operation = getattr(client.web_apps,
                        operation_name if slot is None else operation_name + '_slot')
    if slot is None:
        return (operation(resource_group_name, name)
                if extra_parameter is None else operation(resource_group_name,
                                                          name, extra_parameter))
    return (operation(resource_group_name, name, slot)
            if extra_parameter is None else operation(resource_group_name,
                                                      name, slot, extra_parameter))


def retryable_method(retries=3, interval_sec=5, excpt_type=Exception):
    def decorate(func):
        def call(*args, **kwargs):
            current_retry = retries
            while True:
                try:
                    return func(*args, **kwargs)
                except excpt_type as exception:  # pylint: disable=broad-except
                    current_retry -= 1
                    if current_retry <= 0:
                        raise exception
                time.sleep(interval_sec)
        return call
    return decorate


def get_location_from_resource_group(cli_ctx, resource_group_name):
    client = get_mgmt_service_client(cli_ctx, ResourceType.MGMT_RESOURCE_RESOURCES)
    group = client.resource_groups.get(resource_group_name)
    return group.location


# resource is client.web_apps for webapps, client.app_service_plans for ASPs, etc.
def get_resource_if_exists(resource, **kwargs):
    from azure.core.exceptions import ResourceNotFoundError as R

    try:
        return resource.get(**kwargs)
    except (R, ValueError):
        return None


def generic_settings_operation(cli_ctx, resource_group_name, name, operation_name,
                               setting_properties, slot=None, client=None, api_version=None):
    client = client or web_client_factory(cli_ctx, api_version=api_version)
    operation = getattr(client.web_apps, operation_name if slot is None else operation_name + '_slot')
    if slot is None:
        return operation(resource_group_name, name, setting_properties)

    return operation(resource_group_name, name, slot, setting_properties)


def is_plan_consumption(cmd, plan_info):
    SkuDescription, AppServicePlan = cmd.get_models('SkuDescription', 'AppServicePlan')
    if isinstance(plan_info, AppServicePlan):
        if isinstance(plan_info.sku, SkuDescription):
            return plan_info.sku.tier.lower() == 'dynamic'
    return False


def get_location_from_app(client, resource_group_name, webapp):
    app = client.web_apps.get(resource_group_name, webapp)
    if not app:
        raise ResourceNotFoundError("'{}' app doesn't exist".format(app))
    return app.location


# TODO: remove this when #3660(service tracking issue) is resolved
def _mask_creds_related_appsettings(settings):
    for x in [x1 for x1 in settings if x1 in APPSETTINGS_TO_MASK]:
        settings[x] = None
    return settings


def _build_app_settings_output(app_settings, slot_cfg_names):
    slot_cfg_names = slot_cfg_names or []
    return [{'name': p,
             'value': app_settings[p],
             'slotSetting': p in slot_cfg_names} for p in _mask_creds_related_appsettings(app_settings)]


def _get_app_settings(cmd, resource_group_name, name, slot=None):
    result = generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'list_application_settings', slot)
    client = web_client_factory(cmd.cli_ctx)
    slot_app_setting_names = client.web_apps.list_slot_configuration_names(resource_group_name, name).app_setting_names
    return _build_app_settings_output(result.properties, slot_app_setting_names)


def _delete_app_settings(cmd, resource_group_name, name, setting_names, slot=None):
    app_settings = generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'list_application_settings', slot)
    client = web_client_factory(cmd.cli_ctx)

    slot_cfg_names = client.web_apps.list_slot_configuration_names(resource_group_name, name)
    is_slot_settings = False
    for setting_name in setting_names:
        app_settings.properties.pop(setting_name, None)
        if slot_cfg_names.app_setting_names and setting_name in slot_cfg_names.app_setting_names:
            slot_cfg_names.app_setting_names.remove(setting_name)
            is_slot_settings = True

    if is_slot_settings:
        client.web_apps.update_slot_configuration_names(resource_group_name, name, slot_cfg_names)

    result = generic_settings_operation(cmd.cli_ctx, resource_group_name, name,
                                        'update_application_settings',
                                        app_settings, slot, client)

    return _build_app_settings_output(result.properties, slot_cfg_names.app_setting_names)


# Check if the app setting is propagated to the Kudu site correctly by calling api/settings endpoint
# should_have [] is a list of app settings which are expected to be set
# should_not_have [] is a list of app settings which are expected to be absent
# should_contain {} is a dictionary of app settings which are expected to be set with precise values
# Return True if validation succeeded
def _validate_app_settings_in_scm(cmd, resource_group_name, name, slot=None,
                                  should_have=None, should_not_have=None, should_contain=None):
    scm_settings = _get_app_settings_from_scm(cmd, resource_group_name, name, slot)
    scm_setting_keys = set(scm_settings.keys())

    if should_have and not set(should_have).issubset(scm_setting_keys):
        return False

    if should_not_have and set(should_not_have).intersection(scm_setting_keys):
        return False

    temp_setting = scm_settings.copy()
    temp_setting.update(should_contain or {})
    if temp_setting != scm_settings:
        return False

    return True


def _update_app_settings(cmd, resource_group_name, name, settings=None, slot=None, slot_settings=None):
    if not settings and not slot_settings:
        raise MutuallyExclusiveArgumentError('Usage Error: --settings |--slot-settings')

    settings = settings or []
    slot_settings = slot_settings or []

    app_settings = generic_site_operation(cmd.cli_ctx, resource_group_name, name,
                                          'list_application_settings', slot)
    result, slot_result = {}, {}
    # pylint: disable=too-many-nested-blocks
    for src, dest, setting_type in [(settings, result, "Settings"), (slot_settings, slot_result, "SlotSettings")]:
        for s in src:
            try:
                temp = shell_safe_json_parse(s)
                if isinstance(temp, list):  # a bit messy, but we'd like accept the output of the "list" command
                    for t in temp:
                        if 'slotSetting' in t.keys():
                            slot_result[t['name']] = t['slotSetting']
                        if setting_type == "SlotSettings":
                            slot_result[t['name']] = True
                        result[t['name']] = t['value']
                else:
                    dest.update(temp)
            except CLIError:
                setting_name, value = s.split('=', 1)
                dest[setting_name] = value
                result.update(dest)

    for setting_name, value in result.items():
        app_settings.properties[setting_name] = value
    client = web_client_factory(cmd.cli_ctx)

    result = generic_settings_operation(cmd.cli_ctx, resource_group_name, name,
                                        'update_application_settings',
                                        app_settings, slot, client)


def _get_site_credential(cli_ctx, resource_group_name, name, slot=None):
    creds = generic_site_operation(cli_ctx, resource_group_name, name, 'begin_list_publishing_credentials', slot)
    creds = creds.result()
    return (creds.publishing_user_name, creds.publishing_password)


def _get_scm_url(cmd, resource_group_name, name, slot=None):
    from azure.mgmt.web.models import HostType
    app = generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'get', slot)
    for host in app.host_name_ssl_states or []:
        if host.host_type == HostType.repository:
            return "https://{}".format(host.name)

    # this should not happen, but throw anyway
    raise ResourceNotFoundError('Failed to retrieve Scm Uri')


@retryable_method(3, 5)
def _get_app_settings_from_scm(cmd, resource_group_name, name, slot=None):
    scm_url = _get_scm_url(cmd, resource_group_name, name, slot)
    settings_url = '{}/api/settings'.format(scm_url)
    username, password = _get_site_credential(cmd.cli_ctx, resource_group_name, name, slot)
    headers = {
        'Content-Type': 'application/octet-stream',
        'Cache-Control': 'no-cache',
        'User-Agent': get_az_user_agent()
    }

    import requests
    response = requests.get(settings_url, headers=headers, auth=(username, password), timeout=3)

    return response.json() or {}


def upload_zip_to_storage(cmd, resource_group_name, name, src, slot=None):
    settings = _get_app_settings(cmd, resource_group_name, name, slot)

    storage_connection = None
    for keyval in settings:
        if keyval['name'] == 'AzureWebJobsStorage':
            storage_connection = str(keyval['value'])

    if storage_connection is None:
        raise ResourceNotFoundError('Could not find a \'AzureWebJobsStorage\' application setting')

    container_name = "function-releases"
    blob_name = "{}-{}.zip".format(datetime.datetime.today().strftime('%Y%m%d%H%M%S'), str(uuid.uuid4()))
    BlockBlobService = get_sdk(cmd.cli_ctx, ResourceType.DATA_STORAGE, 'blob#BlockBlobService')
    block_blob_service = BlockBlobService(connection_string=storage_connection)
    if not block_blob_service.exists(container_name):
        block_blob_service.create_container(container_name)

    # https://gist.github.com/vladignatyev/06860ec2040cb497f0f3
    def progress_callback(current, total):
        total_length = 30
        filled_length = int(round(total_length * current) / float(total))
        percents = round(100.0 * current / float(total), 1)
        progress_bar = '=' * filled_length + '-' * (total_length - filled_length)
        progress_message = 'Uploading {} {}%'.format(progress_bar, percents)
        cmd.cli_ctx.get_progress_controller().add(message=progress_message)

    block_blob_service.create_blob_from_path(container_name, blob_name, src, validate_content=True,
                                             progress_callback=progress_callback)

    now = datetime.datetime.utcnow()
    blob_start = now - datetime.timedelta(minutes=10)
    blob_end = now + datetime.timedelta(weeks=520)
    BlobPermissions = get_sdk(cmd.cli_ctx, ResourceType.DATA_STORAGE, 'blob#BlobPermissions')
    blob_token = block_blob_service.generate_blob_shared_access_signature(container_name,
                                                                          blob_name,
                                                                          permission=BlobPermissions(read=True),
                                                                          expiry=blob_end,
                                                                          start=blob_start)

    blob_uri = block_blob_service.make_blob_url(container_name, blob_name, sas_token=blob_token)
    website_run_from_setting = "WEBSITE_RUN_FROM_PACKAGE={}".format(blob_uri)
    _update_app_settings(cmd, resource_group_name, name, settings=[website_run_from_setting], slot=slot)
    client = web_client_factory(cmd.cli_ctx)

    try:
        logger.info('\nSyncing Triggers...')
        if slot is not None:
            client.web_apps.sync_function_triggers_slot(resource_group_name, name, slot)
        else:
            client.web_apps.sync_function_triggers(resource_group_name, name)
    except CloudError as ex:
        # This SDK function throws an error if Status Code is 200
        if ex.status_code != 200:
            raise ex
    except Exception as ex:  # pylint: disable=broad-except
        if ex.response.status_code != 200:
            raise ex


def add_remote_build_app_settings(cmd, resource_group_name, name, slot):
    settings = _get_app_settings(cmd, resource_group_name, name, slot)
    scm_do_build_during_deployment = None
    website_run_from_package = None
    enable_oryx_build = None

    app_settings_should_not_have = []
    app_settings_should_contain = {}

    for keyval in settings:
        value = keyval['value'].lower()
        if keyval['name'] == 'SCM_DO_BUILD_DURING_DEPLOYMENT':
            scm_do_build_during_deployment = value in ('true', '1')
        if keyval['name'] == 'WEBSITE_RUN_FROM_PACKAGE':
            website_run_from_package = value
        if keyval['name'] == 'ENABLE_ORYX_BUILD':
            enable_oryx_build = value

    if scm_do_build_during_deployment is not True:
        logger.warning("Setting SCM_DO_BUILD_DURING_DEPLOYMENT to true")
        _update_app_settings(cmd, resource_group_name, name, [
            "SCM_DO_BUILD_DURING_DEPLOYMENT=true"
        ], slot)
        app_settings_should_contain['SCM_DO_BUILD_DURING_DEPLOYMENT'] = 'true'

    if website_run_from_package:
        logger.warning("Removing WEBSITE_RUN_FROM_PACKAGE app setting")
        _delete_app_settings(cmd, resource_group_name, name, [
            "WEBSITE_RUN_FROM_PACKAGE"
        ], slot)
        app_settings_should_not_have.append('WEBSITE_RUN_FROM_PACKAGE')

    if enable_oryx_build:
        logger.warning("Removing ENABLE_ORYX_BUILD app setting")
        _delete_app_settings(cmd, resource_group_name, name, [
            "ENABLE_ORYX_BUILD"
        ], slot)
        app_settings_should_not_have.append('ENABLE_ORYX_BUILD')

    # Wait for scm site to get the latest app settings
    if app_settings_should_not_have or app_settings_should_contain:
        logger.warning("Waiting SCM site to be updated with the latest app settings")
        scm_is_up_to_date = False
        retries = 10
        while not scm_is_up_to_date and retries >= 0:
            scm_is_up_to_date = _validate_app_settings_in_scm(
                cmd, resource_group_name, name, slot,
                should_contain=app_settings_should_contain,
                should_not_have=app_settings_should_not_have)
            retries -= 1
            time.sleep(5)

        if retries < 0:
            logger.warning("App settings may not be propagated to the SCM site.")


def remove_remote_build_app_settings(cmd, resource_group_name, name, slot):
    settings = _get_app_settings(cmd, resource_group_name, name, slot)
    scm_do_build_during_deployment = None

    app_settings_should_contain = {}

    for keyval in settings:
        if keyval['name'] == 'SCM_DO_BUILD_DURING_DEPLOYMENT':
            value = keyval['value'].lower()
            scm_do_build_during_deployment = value in ('true', '1')

    if scm_do_build_during_deployment is not False:
        logger.warning("Setting SCM_DO_BUILD_DURING_DEPLOYMENT to false")
        _update_app_settings(cmd, resource_group_name, name, [
            "SCM_DO_BUILD_DURING_DEPLOYMENT=false"
        ], slot)
        app_settings_should_contain['SCM_DO_BUILD_DURING_DEPLOYMENT'] = 'false'

    # Wait for scm site to get the latest app settings
    if app_settings_should_contain:
        logger.warning("Waiting SCM site to be updated with the latest app settings")
        scm_is_up_to_date = False
        retries = 10
        while not scm_is_up_to_date and retries >= 0:
            scm_is_up_to_date = _validate_app_settings_in_scm(
                cmd, resource_group_name, name, slot,
                should_contain=app_settings_should_contain)
            retries -= 1
            time.sleep(5)

        if retries < 0:
            logger.warning("App settings may not be propagated to the SCM site")


# TODO: expose new blob support
# pylint: disable=too-many-locals
def _config_diagnostics(cmd, resource_group_name, name, level=None,
                        application_logging=None, web_server_logging=None,
                        docker_container_logging=None, detailed_error_messages=None,
                        failed_request_tracing=None, slot=None):
    from azure.mgmt.web.models import (FileSystemApplicationLogsConfig, ApplicationLogsConfig,
                                       AzureBlobStorageApplicationLogsConfig, SiteLogsConfig,
                                       HttpLogsConfig, FileSystemHttpLogsConfig,
                                       EnabledConfig)
    client = web_client_factory(cmd.cli_ctx)
    # TODO: ensure we call get_site only once
    site = client.web_apps.get(resource_group_name, name)
    if not site:
        raise ResourceNotFoundError("'{}' app doesn't exist".format(name))

    application_logs = None
    if application_logging:
        fs_log = None
        blob_log = None
        level = level if application_logging != 'off' else False
        level = True if level is None else level
        if application_logging in ['filesystem', 'off']:
            fs_log = FileSystemApplicationLogsConfig(level=level)
        if application_logging in ['azureblobstorage', 'off']:
            blob_log = AzureBlobStorageApplicationLogsConfig(level=level, retention_in_days=3,
                                                             sas_url=None)
        application_logs = ApplicationLogsConfig(file_system=fs_log,
                                                 azure_blob_storage=blob_log)

    http_logs = None
    server_logging_option = web_server_logging or docker_container_logging
    if server_logging_option:
        # TODO: az blob storage log config currently not in use, will be impelemented later.
        # Tracked as Issue: #4764 on Github
        filesystem_log_config = None
        turned_on = server_logging_option != 'off'
        if server_logging_option in ['filesystem', 'off']:
            # 100 mb max log size, retention lasts 3 days. Yes we hard code it, portal does too
            filesystem_log_config = FileSystemHttpLogsConfig(retention_in_mb=100, retention_in_days=3,
                                                             enabled=turned_on)
        http_logs = HttpLogsConfig(file_system=filesystem_log_config, azure_blob_storage=None)

    detailed_error_messages_logs = (None if detailed_error_messages is None
                                    else EnabledConfig(enabled=detailed_error_messages))
    failed_request_tracing_logs = (None if failed_request_tracing is None
                                   else EnabledConfig(enabled=failed_request_tracing))
    site_log_config = SiteLogsConfig(application_logs=application_logs,
                                     http_logs=http_logs,
                                     failed_requests_tracing=failed_request_tracing_logs,
                                     detailed_error_messages=detailed_error_messages_logs)

    return generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'update_diagnostic_logs_config',
                                  slot, site_log_config)


def _configure_default_logging(cmd, rg_name, name):
    logger.warning("Configuring default logging for the app, if not already enabled")
    return _config_diagnostics(cmd, rg_name, name,
                               application_logging=True, web_server_logging='filesystem',
                               docker_container_logging='filesystem')


def _check_zip_deployment_status(cmd, rg_name, name, deployment_status_url, authorization, timeout=None):
    import requests
    from azure.cli.core.util import should_disable_connection_verify
    total_trials = (int(timeout) // 2) if timeout else 450
    num_trials = 0
    while num_trials < total_trials:
        time.sleep(2)
        response = requests.get(deployment_status_url, headers=authorization,
                                verify=not should_disable_connection_verify())
        try:
            res_dict = response.json()
        except json.decoder.JSONDecodeError:
            logger.warning("Deployment status endpoint %s returns malformed data. Retrying...", deployment_status_url)
            res_dict = {}
        finally:
            num_trials = num_trials + 1

        if res_dict.get('status', 0) == 3:
            _configure_default_logging(cmd, rg_name, name)
            raise CLIError("Zip deployment failed. {}. Please run the command az webapp log deployment show "
                           "-n {} -g {}".format(res_dict, name, rg_name))
        if res_dict.get('status', 0) == 4:
            break
        if 'progress' in res_dict:
            logger.info(res_dict['progress'])  # show only in debug mode, customers seem to find this confusing
    # if the deployment is taking longer than expected
    if res_dict.get('status', 0) != 4:
        _configure_default_logging(cmd, rg_name, name)
        raise CLIError("""Timeout reached by the command, however, the deployment operation
                       is still on-going. Navigate to your scm site to check the deployment status""")
    return res_dict


def enable_zip_deploy(cmd, resource_group_name, name, src, timeout=None, slot=None):
    logger.warning("Getting scm site credentials for zip deployment")
    user_name, password = _get_site_credential(cmd.cli_ctx, resource_group_name, name, slot)

    try:
        scm_url = _get_scm_url(cmd, resource_group_name, name, slot)
    except ValueError:
        raise ResourceNotFoundError('Failed to fetch scm url for function app')

    zip_url = scm_url + '/api/zipdeploy?isAsync=true'
    deployment_status_url = scm_url + '/api/deployments/latest'

    import urllib3
    authorization = urllib3.util.make_headers(basic_auth='{0}:{1}'.format(user_name, password))
    headers = authorization
    headers['Content-Type'] = 'application/octet-stream'
    headers['Cache-Control'] = 'no-cache'
    headers['User-Agent'] = get_az_user_agent()
    headers['x-ms-client-request-id'] = cmd.cli_ctx.data['headers']['x-ms-client-request-id']
    import requests
    import os
    from azure.cli.core.util import should_disable_connection_verify
    # Read file content
    with open(os.path.realpath(os.path.expanduser(src)), 'rb') as fs:
        zip_content = fs.read()
        logger.warning("Starting zip deployment. This operation can take a while to complete ...")
        res = requests.post(zip_url, data=zip_content, headers=headers, verify=not should_disable_connection_verify())
        logger.warning("Deployment endpoint responded with status code %d", res.status_code)

    # check the status of async deployment
    if res.status_code == 202:
        response = _check_zip_deployment_status(cmd, resource_group_name, name, deployment_status_url,
                                                authorization, timeout)
        return response

    # check if there's an ongoing process
    if res.status_code == 409:
        raise UnclassifiedUserFault("There may be an ongoing deployment or your app setting has "
                                    "WEBSITE_RUN_FROM_PACKAGE. Please track your deployment in {} and ensure the "
                                    "WEBSITE_RUN_FROM_PACKAGE app setting is removed. Use 'az webapp config "
                                    "appsettings list --name MyWebapp --resource-group MyResourceGroup --subscription "
                                    "MySubscription' to list app settings and 'az webapp config appsettings delete "
                                    "--name MyWebApp --resource-group MyResourceGroup --setting-names <setting-names> "
                                    "to delete them.".format(deployment_status_url))

    # check if an error occured during deployment
    if res.status_code:
        raise AzureInternalError("An error occured during deployment. Status Code: {}, Details: {}"
                                 .format(res.status_code, res.text))


def is_plan_elastic_premium(cmd, plan_info):
    SkuDescription, AppServicePlan = cmd.get_models('SkuDescription', 'AppServicePlan')
    if isinstance(plan_info, AppServicePlan):
        if isinstance(plan_info.sku, SkuDescription):
            return plan_info.sku.tier == 'ElasticPremium'
    return False


def validate_plan_switch_compatibility(cmd, client, src_functionapp_instance, dest_plan_instance, force):
    general_switch_msg = 'Currently the switch is only allowed between a Consumption or an Elastic Premium plan.'
    src_parse_result = parse_resource_id(src_functionapp_instance.server_farm_id)
    src_plan_info = client.app_service_plans.get(src_parse_result['resource_group'],
                                                 src_parse_result['name'])

    if src_plan_info is None:
        raise ResourceNotFoundError('Could not determine the current plan of the functionapp')

    # Ensure all plans involved are windows. Reserved = true indicates Linux.
    if src_plan_info.reserved or dest_plan_instance.reserved:
        raise ValidationError('This feature currently supports windows to windows plan migrations. For other '
                              'migrations, please redeploy.')

    src_is_premium = is_plan_elastic_premium(cmd, src_plan_info)
    dest_is_consumption = is_plan_consumption(cmd, dest_plan_instance)

    if not (is_plan_consumption(cmd, src_plan_info) or src_is_premium):
        raise ValidationError('Your functionapp is not using a Consumption or an Elastic Premium plan. ' +
                              general_switch_msg)
    if not (dest_is_consumption or is_plan_elastic_premium(cmd, dest_plan_instance)):
        raise ValidationError('You are trying to move to a plan that is not a Consumption or an '
                              'Elastic Premium plan. ' +
                              general_switch_msg)

    if src_is_premium and dest_is_consumption:
        logger.warning('WARNING: Moving a functionapp from Premium to Consumption might result in loss of '
                       'functionality and cause the app to break. Please ensure the functionapp is compatible '
                       'with a Consumption plan and is not using any features only available in Premium.')
        if not force:
            raise RequiredArgumentMissingError('If you want to migrate a functionapp from a Premium to Consumption '
                                               'plan, please re-run this command with the \'--force\' flag.')


def rename_server_farm_props(app):
    # Should be renamed in SDK in a future release
    setattr(app, 'app_service_plan_id', app.server_farm_id)
    del app.server_farm_id
    return app


def _list_publish_profiles(cmd, resource_group_name, name, slot=None, xml=False):
    import xmltodict
    content = generic_site_operation(cmd.cli_ctx, resource_group_name, name,
                                     'list_publishing_profile_xml_with_secrets', slot, {"format": "WebDeploy"})
    full_xml = ''
    for f in content:
        full_xml += f.decode()

    if not xml:
        profiles = xmltodict.parse(full_xml, xml_attribs=True)['publishData']['publishProfile']
        converted = []

        if not isinstance(profiles, list):
            profiles = [profiles]

        for profile in profiles:
            new = {}
            for key in profile:
                # strip the leading '@' xmltodict put in for attributes
                new[key.lstrip('@')] = profile[key]
            converted.append(new)
        return converted

    cmd.cli_ctx.invocation.data['output'] = 'tsv'
    return full_xml


def fill_ftp_publishing_url(cmd, app, resource_group_name, name, slot=None):
    profiles = _list_publish_profiles(cmd, resource_group_name, name, slot)
    try:
        url = next(p['publishUrl'] for p in profiles if p['publishMethod'] == 'FTP')
        setattr(app, 'ftpPublishingUrl', url)
    except StopIteration:
        pass
    return app


# TODO limit to only logic apps?
def list_app(cli_ctx, resource_group_name=None):
    client = web_client_factory(cli_ctx)
    if resource_group_name:
        result = list(client.web_apps.list_by_resource_group(resource_group_name))
    else:
        result = list(client.web_apps.list())
    for app in result:
        rename_server_farm_props(app)
    return result


def format_fx_version(custom_image_name, container_config_type=None):
    lower_custom_image_name = custom_image_name.lower()
    if "https://" in lower_custom_image_name or "http://" in lower_custom_image_name:
        custom_image_name = lower_custom_image_name.replace("https://", "").replace("http://", "")
    fx_version = custom_image_name.strip()
    fx_version_lower = fx_version.lower()
    # handles case of only spaces
    if fx_version:
        if container_config_type:
            fx_version = '{}|{}'.format(container_config_type, custom_image_name)
        elif not fx_version_lower.startswith('docker|'):
            fx_version = '{}|{}'.format('DOCKER', custom_image_name)
    else:
        fx_version = ' '
    return fx_version


def get_extension_version_functionapp(functions_version):
    if functions_version is not None:
        return '~{}'.format(functions_version)
    return '~2'


def get_app_insights_key(cli_ctx, resource_group, name):
    appinsights_client = get_mgmt_service_client(cli_ctx, ApplicationInsightsManagementClient)
    appinsights = appinsights_client.components.get(resource_group, name)
    if appinsights is None or appinsights.instrumentation_key is None:
        raise ResourceNotFoundError("App Insights {} under resource group {} was not found.".format(name,
                                                                                                    resource_group))
    return appinsights.instrumentation_key


def parse_docker_image_name(deployment_container_image_name):
    if not deployment_container_image_name:
        return None
    non_url = "/" not in deployment_container_image_name
    non_url = non_url or ("." not in deployment_container_image_name and ":" not in deployment_container_image_name)
    if non_url:
        return None
    parsed_url = urlparse(deployment_container_image_name)
    if parsed_url.scheme:
        return parsed_url.hostname
    hostname = urlparse("https://{}".format(deployment_container_image_name)).hostname
    return "https://{}".format(hostname)


def validate_and_get_connection_string(cli_ctx, resource_group_name, storage_account):
    sa_resource_group = resource_group_name
    if is_valid_resource_id(storage_account):
        sa_resource_group = parse_resource_id(storage_account)['resource_group']
        storage_account = parse_resource_id(storage_account)['name']
    storage_client = get_mgmt_service_client(cli_ctx, StorageManagementClient)
    storage_properties = storage_client.storage_accounts.get_properties(sa_resource_group,
                                                                        storage_account)
    error_message = ''
    endpoints = storage_properties.primary_endpoints
    sku = storage_properties.sku.name
    allowed_storage_types = ['Standard_GRS', 'Standard_RAGRS', 'Standard_LRS', 'Standard_ZRS', 'Premium_LRS', 'Standard_GZRS']  # pylint: disable=line-too-long

    for e in ['blob', 'queue', 'table']:
        if not getattr(endpoints, e, None):
            error_message = "Storage account '{}' has no '{}' endpoint. It must have table, queue, and blob endpoints all enabled".format(storage_account, e)   # pylint: disable=line-too-long
    if sku not in allowed_storage_types:
        error_message += 'Storage type {} is not allowed'.format(sku)

    if error_message:
        raise CLIError(error_message)

    obj = storage_client.storage_accounts.list_keys(sa_resource_group, storage_account)  # pylint: disable=no-member
    try:
        keys = [obj.keys[0].value, obj.keys[1].value]  # pylint: disable=no-member
    except AttributeError:
        # Older API versions have a slightly different structure
        keys = [obj.key1, obj.key2]  # pylint: disable=no-member

    endpoint_suffix = cli_ctx.cloud.suffixes.storage_endpoint
    connection_string = 'DefaultEndpointsProtocol={};EndpointSuffix={};AccountName={};AccountKey={}'.format(
        "https",
        endpoint_suffix,
        storage_account,
        keys[0])  # pylint: disable=no-member

    return connection_string


def _get_acr_cred(cli_ctx, registry_name):
    from azure.mgmt.containerregistry import ContainerRegistryManagementClient
    from azure.cli.core.commands.parameters import get_resources_in_subscription
    client = get_mgmt_service_client(cli_ctx, ContainerRegistryManagementClient).registries

    result = get_resources_in_subscription(cli_ctx, 'Microsoft.ContainerRegistry/registries')
    result = [item for item in result if item.name.lower() == registry_name]
    if not result or len(result) > 1:
        raise ResourceNotFoundError(f"No resource or more than one were found with name '{registry_name}'.")
    resource_group_name = parse_resource_id(result[0].id)['resource_group']

    registry = client.get(resource_group_name, registry_name)

    if registry.admin_user_enabled:  # pylint: disable=no-member
        cred = client.list_credentials(resource_group_name, registry_name)
        return cred.username, cred.passwords[0].value
    raise ResourceNotFoundError("Failed to retrieve container registry credentials. Please either provide the "
                                "credentials or run 'az acr update -n {} --admin-enabled true' to enable "
                                "admin first.".format(registry_name))


# for any modifications to the non-optional parameters, adjust the reflection logic accordingly
# in the method
# pylint: disable=unused-argument
def update_site_configs(cmd, resource_group_name, name, slot=None, number_of_workers=None, linux_fx_version=None,
                        windows_fx_version=None, pre_warmed_instance_count=None, php_version=None,
                        python_version=None, net_framework_version=None,
                        java_version=None, java_container=None, java_container_version=None,
                        remote_debugging_enabled=None, web_sockets_enabled=None,
                        always_on=None, auto_heal_enabled=None,
                        use32_bit_worker_process=None,
                        min_tls_version=None,
                        http20_enabled=None,
                        app_command_line=None,
                        ftps_state=None,
                        vnet_route_all_enabled=None,
                        generic_configurations=None):
    configs = get_site_configs(cmd, resource_group_name, name, slot)
    app_settings = generic_site_operation(cmd.cli_ctx, resource_group_name, name,
                                          'list_application_settings', slot)
    if number_of_workers is not None:
        number_of_workers = validate_range_of_int_flag('--number-of-workers', number_of_workers, min_val=0, max_val=20)
    if linux_fx_version:
        if linux_fx_version.strip().lower().startswith('docker|'):
            if ('WEBSITES_ENABLE_APP_SERVICE_STORAGE' not in app_settings.properties or
                    app_settings.properties['WEBSITES_ENABLE_APP_SERVICE_STORAGE'] != 'true'):
                update_app_settings(cmd, resource_group_name, name, ["WEBSITES_ENABLE_APP_SERVICE_STORAGE=false"])
        else:
            delete_app_settings(cmd, resource_group_name, name, ["WEBSITES_ENABLE_APP_SERVICE_STORAGE"])

    if pre_warmed_instance_count is not None:
        pre_warmed_instance_count = validate_range_of_int_flag('--prewarmed-instance-count', pre_warmed_instance_count,
                                                               min_val=0, max_val=20)
    import inspect
    frame = inspect.currentframe()
    bool_flags = ['remote_debugging_enabled', 'web_sockets_enabled', 'always_on',
                  'auto_heal_enabled', 'use32_bit_worker_process', 'http20_enabled', 'vnet_route_all_enabled']
    int_flags = ['pre_warmed_instance_count', 'number_of_workers']
    # note: getargvalues is used already in azure.cli.core.commands.
    # and no simple functional replacement for this deprecating method for 3.5
    args, _, _, values = inspect.getargvalues(frame)  # pylint: disable=deprecated-method
    for arg in args[3:]:
        if arg in int_flags and values[arg] is not None:
            values[arg] = validate_and_convert_to_int(arg, values[arg])
        if arg != 'generic_configurations' and values.get(arg, None):
            setattr(configs, arg, values[arg] if arg not in bool_flags else values[arg] == 'true')

    generic_configurations = generic_configurations or []
    # https://github.com/Azure/azure-cli/issues/14857
    updating_ip_security_restrictions = False

    result = {}
    for s in generic_configurations:
        try:
            json_object = get_json_object(s)
            for config_name in json_object:
                if config_name.lower() == 'ip_security_restrictions':
                    updating_ip_security_restrictions = True
            result.update(json_object)
        except CLIError:
            config_name, value = s.split('=', 1)
            result[config_name] = value

    for config_name, value in result.items():
        if config_name.lower() == 'ip_security_restrictions':
            updating_ip_security_restrictions = True
        setattr(configs, config_name, value)

    if not updating_ip_security_restrictions:
        setattr(configs, 'ip_security_restrictions', None)
        setattr(configs, 'scm_ip_security_restrictions', None)
    return generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'update_configuration', slot, configs)


def _add_fx_version(cmd, resource_group_name, name, custom_image_name, slot=None):
    fx_version = format_fx_version(custom_image_name)
    app = generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'get', slot)
    if not app:
        raise ResourceNotFoundError("'{}' app doesn't exist in resource group {}".format(name, resource_group_name))
    linux_fx = fx_version if (app.reserved or not app.is_xenon) else None
    windows_fx = fx_version if app.is_xenon else None
    return update_site_configs(cmd, resource_group_name, name,
                               linux_fx_version=linux_fx, windows_fx_version=windows_fx, slot=slot)


def _get_fx_version(cmd, resource_group_name, name, slot=None):
    site_config = get_site_configs(cmd, resource_group_name, name, slot)
    return site_config.linux_fx_version or site_config.windows_fx_version or ''


def _get_linux_multicontainer_decoded_config(cmd, resource_group_name, name, slot=None):
    from base64 import b64decode
    linux_fx_version = _get_fx_version(cmd, resource_group_name, name, slot)
    if not any(linux_fx_version.startswith(s) for s in MULTI_CONTAINER_TYPES):
        raise ValidationError("Cannot decode config that is not one of the"
                              " following types: {}".format(','.join(MULTI_CONTAINER_TYPES)))
    return b64decode(linux_fx_version.split('|')[1].encode('utf-8'))


def _filter_for_container_settings(cmd, resource_group_name, name, settings,
                                   show_multicontainer_config=None, slot=None):
    result = [x for x in settings if x['name'] in CONTAINER_APPSETTING_NAMES]
    fx_version = _get_fx_version(cmd, resource_group_name, name, slot).strip()
    if fx_version:
        added_image_name = {'name': 'DOCKER_CUSTOM_IMAGE_NAME',
                            'value': fx_version}
        result.append(added_image_name)
        if show_multicontainer_config:
            decoded_value = _get_linux_multicontainer_decoded_config(cmd, resource_group_name, name, slot)
            decoded_image_name = {'name': 'DOCKER_CUSTOM_IMAGE_NAME_DECODED',
                                  'value': decoded_value}
            result.append(decoded_image_name)
    return result


def url_validator(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc, result.path])
    except ValueError:
        return False


def _ssl_context():
    if sys.version_info < (3, 4) or (in_cloud_console() and sys.platform.system() == 'Windows'):
        try:
            return ssl.SSLContext(ssl.PROTOCOL_TLS)  # added in python 2.7.13 and 3.6
        except AttributeError:
            return ssl.SSLContext(ssl.PROTOCOL_TLSv1)

    return ssl.create_default_context()


def _get_linux_multicontainer_encoded_config_from_file(file_name):
    from base64 import b64encode
    config_file_bytes = None
    if url_validator(file_name):
        response = urlopen(file_name, context=_ssl_context())
        config_file_bytes = response.read()
    else:
        with open(file_name, 'rb') as f:
            config_file_bytes = f.read()
    # Decode base64 encoded byte array into string
    return b64encode(config_file_bytes).decode('utf-8')


def _update_container_settings(cmd, resource_group_name, name, docker_registry_server_url=None,
                               docker_custom_image_name=None, docker_registry_server_user=None,
                               websites_enable_app_service_storage=None, docker_registry_server_password=None,
                               multicontainer_config_type=None, multicontainer_config_file=None, slot=None):
    settings = []
    if docker_registry_server_url is not None:
        settings.append('DOCKER_REGISTRY_SERVER_URL=' + docker_registry_server_url)

    if (not docker_registry_server_user and not docker_registry_server_password and
            docker_registry_server_url and '.azurecr.io' in docker_registry_server_url):
        logger.warning('No credential was provided to access Azure Container Registry. Trying to look up...')
        parsed = urlparse(docker_registry_server_url)
        registry_name = (parsed.netloc if parsed.scheme else parsed.path).split('.')[0]
        try:
            docker_registry_server_user, docker_registry_server_password = _get_acr_cred(cmd.cli_ctx, registry_name)
        except Exception as ex:  # pylint: disable=broad-except
            logger.warning("Retrieving credentials failed with an exception:'%s'", ex)  # consider throw if needed

    if docker_registry_server_user is not None:
        settings.append('DOCKER_REGISTRY_SERVER_USERNAME=' + docker_registry_server_user)
    if docker_registry_server_password is not None:
        settings.append('DOCKER_REGISTRY_SERVER_PASSWORD=' + docker_registry_server_password)
    if websites_enable_app_service_storage:
        settings.append('WEBSITES_ENABLE_APP_SERVICE_STORAGE=' + websites_enable_app_service_storage)

    if docker_registry_server_user or docker_registry_server_password or docker_registry_server_url or websites_enable_app_service_storage:  # pylint: disable=line-too-long
        update_app_settings(cmd, resource_group_name, name, settings, slot)
    settings = get_app_settings(cmd, resource_group_name, name, slot)
    if docker_custom_image_name is not None:
        _add_fx_version(cmd, resource_group_name, name, docker_custom_image_name, slot)

    if multicontainer_config_file and multicontainer_config_type:
        encoded_config_file = _get_linux_multicontainer_encoded_config_from_file(multicontainer_config_file)
        linux_fx_version = format_fx_version(encoded_config_file, multicontainer_config_type)
        update_site_configs(cmd, resource_group_name, name, linux_fx_version=linux_fx_version, slot=slot)
    elif multicontainer_config_file or multicontainer_config_type:
        logger.warning('Must change both settings --multicontainer-config-file FILE --multicontainer-config-type TYPE')

    return _mask_creds_related_appsettings(_filter_for_container_settings(cmd, resource_group_name, name, settings,
                                                                          slot=slot))


def update_container_settings_logicapp(cmd, resource_group_name, name, docker_registry_server_url=None,
                                       docker_custom_image_name=None, docker_registry_server_user=None,
                                       docker_registry_server_password=None, slot=None):
    return _update_container_settings(cmd, resource_group_name, name, docker_registry_server_url,
                                      docker_custom_image_name, docker_registry_server_user, None,
                                      docker_registry_server_password, multicontainer_config_type=None,
                                      multicontainer_config_file=None, slot=slot)


def try_create_application_insights(cmd, functionapp):
    creation_failed_warn = 'Unable to create the Application Insights for the Function App. ' \
                           'Please use the Azure Portal to manually create and configure the Application Insights, ' \
                           'if needed.'

    ai_resource_group_name = functionapp.resource_group
    ai_name = functionapp.name
    ai_location = functionapp.location

    app_insights_client = get_mgmt_service_client(cmd.cli_ctx, ApplicationInsightsManagementClient)
    ai_properties = {
        "name": ai_name,
        "location": ai_location,
        "kind": "web",
        "properties": {
            "Application_Type": "web"
        }
    }
    appinsights = app_insights_client.components.create_or_update(ai_resource_group_name, ai_name, ai_properties)
    if appinsights is None or appinsights.instrumentation_key is None:
        logger.warning(creation_failed_warn)
        return

    # We make this success message as a warning to no interfere with regular JSON output in stdout
    logger.warning('Application Insights \"%s\" was created for this Function App. '
                   'You can visit https://portal.azure.com/#resource%s/overview to view your '
                   'Application Insights component', appinsights.name, appinsights.id)

    update_app_settings(cmd, functionapp.resource_group, functionapp.name,
                        ['APPINSIGHTS_INSTRUMENTATIONKEY={}'.format(appinsights.instrumentation_key)])


def _get_local_git_url(cli_ctx, client, resource_group_name, name, slot=None):
    user = client.get_publishing_user()
    result = generic_site_operation(cli_ctx, resource_group_name, name, 'get_source_control', slot)
    parsed = urlparse(result.repo_url)
    return '{}://{}@{}/{}.git'.format(parsed.scheme, user.publishing_user_name,
                                      parsed.netloc, name)


def _enable_local_git(cmd, resource_group_name, name, slot=None):
    client = web_client_factory(cmd.cli_ctx)
    site_config = get_site_configs(cmd, resource_group_name, name, slot)
    site_config.scm_type = 'LocalGit'
    generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'create_or_update_configuration', slot, site_config)
    return {'url': _get_local_git_url(cmd.cli_ctx, client, resource_group_name, name, slot)}


def config_source_control(cmd, resource_group_name, name, repo_url, repository_type='git', branch=None,  # pylint: disable=too-many-locals
                          manual_integration=None, git_token=None, slot=None, github_action=None):
    client = web_client_factory(cmd.cli_ctx)
    location = get_location_from_app(client, resource_group_name, name)

    from azure.mgmt.web.models import SiteSourceControl, SourceControl
    if git_token:
        sc = SourceControl(location=location, source_control_name='GitHub', token=git_token)
        client.update_source_control('GitHub', sc)

    source_control = SiteSourceControl(location=location, repo_url=repo_url, branch=branch,
                                       is_manual_integration=manual_integration,
                                       is_mercurial=(repository_type != 'git'), is_git_hub_action=bool(github_action))

    # SCC config can fail if previous commands caused SCMSite shutdown, so retry here.
    for i in range(5):
        try:
            poller = generic_site_operation(cmd.cli_ctx, resource_group_name, name,
                                            'begin_create_or_update_source_control',
                                            slot, source_control)
            return LongRunningOperation(cmd.cli_ctx)(poller)
        except Exception as ex:  # pylint: disable=broad-except
            ex = ex_handler_factory(no_throw=True)(ex)
            # for non server errors(50x), just throw; otherwise retry 4 times
            if i == 4 or not re.findall(r'\(50\d\)', str(ex)):
                raise
            logger.warning('retrying %s/4', i + 1)
            time.sleep(5)   # retry in a moment


def set_remote_or_local_git(cmd, webapp, resource_group_name, name, deployment_source_url=None,
                            deployment_source_branch='master', deployment_local_git=None):
    if deployment_source_url:
        logger.warning("Linking to git repository '%s'", deployment_source_url)
        try:
            config_source_control(cmd, resource_group_name, name, deployment_source_url, 'git',
                                  deployment_source_branch, manual_integration=True)
        except Exception as ex:  # pylint: disable=broad-except
            ex = ex_handler_factory(no_throw=True)(ex)
            logger.warning("Link to git repository failed due to error '%s'", ex)

    if deployment_local_git:
        local_git_info = _enable_local_git(cmd, resource_group_name, name)
        logger.warning("Local git is configured with url of '%s'", local_git_info['url'])
        setattr(webapp, 'deploymentLocalGitUrl', local_git_info['url'])


def create_logicapp_app_service_plan(cmd, resource_group_name, name, location=None):
    SkuDescription, AppServicePlan = cmd.get_models('SkuDescription', 'AppServicePlan')

    client = web_client_factory(cmd.cli_ctx)

    ase_def = None
    if location is None:
        location = get_location_from_resource_group(cmd.cli_ctx, resource_group_name)

    # the api is odd on parameter naming, have to live with it for now
    sku_def = SkuDescription(tier="WorkflowStandard", name="WS1", capacity=None)
    plan_def = AppServicePlan(location=location, tags=None, sku=sku_def,
                              reserved=None, hyper_v=None, name=name,
                              per_site_scaling=False, hosting_environment_profile=ase_def)

    existing_plan = get_resource_if_exists(client.app_service_plans,
                                           resource_group_name=resource_group_name, name=name)
    if existing_plan and existing_plan.sku.tier != "WorkflowStandard":
        raise ValidationError("Plan {} in resource group {} already exists and "
                              "cannot be updated to a logic app SKU (WS1, WS2, or WS3)")
    plan_def.type = "elastic"

    return client.app_service_plans.begin_create_or_update(name=name,
                                                           resource_group_name=resource_group_name,
                                                           app_service_plan=plan_def)


def get_site_configs(cmd, resource_group_name, name, slot=None):
    return generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'get_configuration', slot)


def get_app_settings(cmd, resource_group_name, name, slot=None):
    result = generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'list_application_settings', slot)
    client = web_client_factory(cmd.cli_ctx)
    slot_app_setting_names = client.web_apps.list_slot_configuration_names(resource_group_name, name).app_setting_names
    return _build_app_settings_output(result.properties, slot_app_setting_names)


def delete_app_settings(cmd, resource_group_name, name, setting_names, slot=None):
    app_settings = generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'list_application_settings', slot)
    client = web_client_factory(cmd.cli_ctx)

    slot_cfg_names = client.web_apps.list_slot_configuration_names(resource_group_name, name)
    is_slot_settings = False
    for setting_name in setting_names:
        app_settings.properties.pop(setting_name, None)
        if slot_cfg_names.app_setting_names and setting_name in slot_cfg_names.app_setting_names:
            slot_cfg_names.app_setting_names.remove(setting_name)
            is_slot_settings = True

    if is_slot_settings:
        client.web_apps.update_slot_configuration_names(resource_group_name, name, slot_cfg_names)

    result = generic_settings_operation(cmd.cli_ctx, resource_group_name, name,
                                        'update_application_settings',
                                        app_settings, slot, client)

    return _build_app_settings_output(result.properties, slot_cfg_names.app_setting_names)


def update_app_settings(cmd, resource_group_name, name, settings=None, slot=None, slot_settings=None):
    if not settings and not slot_settings:
        raise MutuallyExclusiveArgumentError('Usage Error: --settings |--slot-settings')

    settings = settings or []
    slot_settings = slot_settings or []

    app_settings = generic_site_operation(cmd.cli_ctx, resource_group_name, name,
                                          'list_application_settings', slot)
    result, slot_result = {}, {}
    # pylint: disable=too-many-nested-blocks
    for src, dest, setting_type in [(settings, result, "Settings"), (slot_settings, slot_result, "SlotSettings")]:
        for s in src:
            try:
                temp = shell_safe_json_parse(s)
                if isinstance(temp, list):  # a bit messy, but we'd like accept the output of the "list" command
                    for t in temp:
                        if 'slotSetting' in t.keys():
                            slot_result[t['name']] = t['slotSetting']
                        if setting_type == "SlotSettings":
                            slot_result[t['name']] = True
                        result[t['name']] = t['value']
                else:
                    dest.update(temp)
            except CLIError:
                setting_name, value = s.split('=', 1)
                dest[setting_name] = value
                result.update(dest)

    for setting_name, value in result.items():
        app_settings.properties[setting_name] = value
    client = web_client_factory(cmd.cli_ctx)

    result = generic_settings_operation(cmd.cli_ctx, resource_group_name, name,
                                        'update_application_settings',
                                        app_settings, slot, client)

    app_settings_slot_cfg_names = []
    if slot_result:
        slot_cfg_names = client.web_apps.list_slot_configuration_names(resource_group_name, name)
        slot_cfg_names.app_setting_names = slot_cfg_names.app_setting_names or []
        # Slot settings logic to add a new setting(s) or remove an existing setting(s)
        for slot_setting_name, value in slot_result.items():
            if value and slot_setting_name not in slot_cfg_names.app_setting_names:
                slot_cfg_names.app_setting_names.append(slot_setting_name)
            elif not value and slot_setting_name in slot_cfg_names.app_setting_names:
                slot_cfg_names.app_setting_names.remove(slot_setting_name)
        app_settings_slot_cfg_names = slot_cfg_names.app_setting_names
        client.web_apps.update_slot_configuration_names(resource_group_name, name, slot_cfg_names)

    return _build_app_settings_output(result.properties, app_settings_slot_cfg_names)
