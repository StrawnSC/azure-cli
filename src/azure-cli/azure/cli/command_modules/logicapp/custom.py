# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
# pylint: disable=unused-argument

from binascii import hexlify
from os import urandom
import time

from knack.log import get_logger

from msrestazure.tools import is_valid_resource_id, parse_resource_id

from azure.cli.core.commands import LongRunningOperation
from azure.cli.core.azclierror import MutuallyExclusiveArgumentError, ResourceNotFoundError

from ._utils import (is_plan_consumption,
                     upload_zip_to_storage,
                     add_remote_build_app_settings,
                     remove_remote_build_app_settings,
                     enable_zip_deploy,
                     generic_site_operation,
                     validate_plan_switch_compatibility,
                     list_app,
                     is_plan_elastic_premium,
                     rename_server_farm_props,
                     fill_ftp_publishing_url,
                     format_fx_version,
                     get_extension_version_functionapp,
                     get_app_insights_key,
                     parse_docker_image_name,
                     validate_and_get_connection_string,
                     update_container_settings_logicapp,
                     try_create_application_insights,
                     set_remote_or_local_git,
                     create_logicapp_app_service_plan,
                     get_site_configs,
                     update_app_settings,
                     delete_app_settings,
                     get_app_settings
                     )

from ._client_factory import web_client_factory

from ._constants import (DEFAULT_LOGICAPP_FUNCTION_VERSION,
                         DEFAULT_LOGICAPP_RUNTIME,
                         DEFAULT_LOGICAPP_RUNTIME_VERSION,
                         FUNCTIONS_VERSION_TO_DEFAULT_RUNTIME_VERSION,
                         DOTNET_RUNTIME_VERSION_TO_DOTNET_LINUX_FX_VERSION)

logger = get_logger(__name__)


def create_logicapp(cmd, resource_group_name, name, storage_account, plan=None,
                    app_insights=None, app_insights_key=None, disable_app_insights=None,
                    deployment_source_url=None, deployment_source_branch='master', deployment_local_git=None,
                    docker_registry_server_password=None, docker_registry_server_user=None,
                    deployment_container_image_name=None, tags=None, https_only=False):
    # pylint: disable=too-many-statements, too-many-branches, too-many-locals
    functions_version = DEFAULT_LOGICAPP_FUNCTION_VERSION
    runtime = None
    runtime_version = None

    if not deployment_container_image_name:
        runtime = DEFAULT_LOGICAPP_RUNTIME
        runtime_version = DEFAULT_LOGICAPP_RUNTIME_VERSION

    if deployment_source_url and deployment_local_git:
        raise MutuallyExclusiveArgumentError('usage error: --deployment-source-url <url> | --deployment-local-git')

    SiteConfig, Site, NameValuePair = cmd.get_models('SiteConfig', 'Site', 'NameValuePair')

    docker_registry_server_url = parse_docker_image_name(
        deployment_container_image_name)

    site_config = SiteConfig(app_settings=[])
    logicapp_def = Site(location=None, site_config=site_config, tags=tags, https_only=https_only)
    client = web_client_factory(cmd.cli_ctx)
    plan_info = None
    if runtime is not None:
        runtime = runtime.lower()

    logicapp_def.kind = 'functionapp,workflowapp'

    if not plan:  # no plan passed in, so create a WS1 ASP
        plan_name = "{}_app_service_plan".format(name)
        create_logicapp_app_service_plan(cmd, resource_group_name, plan_name)
        logger.warning("Created App Service Plan %s in resource group %s", plan_name, resource_group_name)
        plan_info = client.app_service_plans.get(resource_group_name, plan_name)
    else:  # apps with SKU based plan
        if is_valid_resource_id(plan):
            parse_result = parse_resource_id(plan)
            plan_info = client.app_service_plans.get(parse_result['resource_group'], parse_result['name'])
        else:
            plan_info = client.app_service_plans.get(resource_group_name, plan)

    is_linux = plan_info.reserved
    logicapp_def.server_farm_id = plan_info.id
    logicapp_def.location = plan_info.location

    if runtime:
        site_config.app_settings.append(NameValuePair(
            name='FUNCTIONS_WORKER_RUNTIME', value=runtime))

    con_string = validate_and_get_connection_string(cmd.cli_ctx, resource_group_name, storage_account)

    if is_linux:
        logicapp_def.kind = 'functionapp,workflowapp,linux'
        logicapp_def.reserved = True

    site_config.app_settings.append(NameValuePair(name='MACHINEKEY_DecryptionKey',
                                                  value=str(hexlify(urandom(32)).decode()).upper()))
    if deployment_container_image_name:
        logicapp_def.kind = 'functionapp,workflowapp,linux,container'
        site_config.app_settings.append(NameValuePair(name='DOCKER_CUSTOM_IMAGE_NAME',
                                                      value=deployment_container_image_name))
        site_config.app_settings.append(NameValuePair(name='FUNCTION_APP_EDIT_MODE', value='readOnly'))
        site_config.app_settings.append(NameValuePair(name='WEBSITES_ENABLE_APP_SERVICE_STORAGE',
                                                      value='false'))
        site_config.linux_fx_version = format_fx_version(deployment_container_image_name)

        if deployment_container_image_name is None:
            site_config.linux_fx_version = _get_linux_fx_functionapp(
                functions_version, runtime, runtime_version)
        else:
            logicapp_def.kind = 'functionapp,workflowapp'

    # adding appsetting to site to make it a workflow
    site_config.app_settings.append(NameValuePair(name='FUNCTIONS_EXTENSION_VERSION',
                                                  value=get_extension_version_functionapp(functions_version)))
    site_config.app_settings.append(NameValuePair(name='AzureWebJobsStorage', value=con_string))
    site_config.app_settings.append(NameValuePair(name='AzureWebJobsDashboard', value=con_string))
    site_config.app_settings.append(NameValuePair(
        name='AzureFunctionsJobHost__extensionBundle__id', value="Microsoft.Azure.Functions.ExtensionBundle.Workflows"))
    site_config.app_settings.append(NameValuePair(
        name='AzureFunctionsJobHost__extensionBundle__version', value="[1.*, 2.0.0)"))
    site_config.app_settings.append(
        NameValuePair(name='APP_KIND', value="workflowApp"))

    # If plan is not consumption or elastic premium or workflow standard, we need to set always on
    if (not is_plan_elastic_premium(cmd, plan_info) and not is_plan_workflow_standard(cmd, plan_info) and not
            is_plan_ASEV3(cmd, plan_info)):
        site_config.always_on = True

    # If plan is elastic premium or windows consumption, we need these app settings
    if is_plan_elastic_premium(cmd, plan_info):
        site_config.app_settings.append(NameValuePair(name='WEBSITE_CONTENTAZUREFILECONNECTIONSTRING',
                                                      value=con_string))
        site_config.app_settings.append(NameValuePair(
            name='WEBSITE_CONTENTSHARE', value=name.lower()))

    create_app_insights = False

    if app_insights_key is not None:
        site_config.app_settings.append(NameValuePair(name='APPINSIGHTS_INSTRUMENTATIONKEY',
                                                      value=app_insights_key))
    elif app_insights is not None:
        instrumentation_key = get_app_insights_key(
            cmd.cli_ctx, resource_group_name, app_insights)
        site_config.app_settings.append(NameValuePair(name='APPINSIGHTS_INSTRUMENTATIONKEY',
                                                      value=instrumentation_key))
    elif not disable_app_insights:
        create_app_insights = True

    poller = client.web_apps.begin_create_or_update(
        resource_group_name, name, logicapp_def)
    logicapp = LongRunningOperation(cmd.cli_ctx)(poller)

    set_remote_or_local_git(cmd, logicapp, resource_group_name, name, deployment_source_url,
                            deployment_source_branch, deployment_local_git)

    if create_app_insights:
        try:
            try_create_application_insights(cmd, logicapp)
        except Exception:  # pylint: disable=broad-except
            logger.warning('Error while trying to create and configure an Application Insights for the Logic App. '
                           'Please use the Azure Portal to create and configure the Application Insights, if needed.')

    if deployment_container_image_name:
        update_container_settings_logicapp(cmd, resource_group_name, name, docker_registry_server_url,
                                           deployment_container_image_name, docker_registry_server_user,
                                           docker_registry_server_password)

    return logicapp


def is_plan_workflow_standard(cmd, plan_info):
    SkuDescription, AppServicePlan = cmd.get_models('SkuDescription', 'AppServicePlan')
    if isinstance(plan_info, AppServicePlan):
        if isinstance(plan_info.sku, SkuDescription):
            return plan_info.sku.tier == 'WorkflowStandard'
    return False


def is_plan_ASEV3(cmd, plan_info):
    SkuDescription, AppServicePlan = cmd.get_models('SkuDescription', 'AppServicePlan')
    if isinstance(plan_info, AppServicePlan):
        if isinstance(plan_info.sku, SkuDescription):
            return plan_info.sku.tier == 'IsolatedV2'
    return False


def list_logicapp(cmd, resource_group_name=None):
    return list(filter(lambda x: x.kind is not None and "workflow" in x.kind.lower(),
                       list_app(cmd.cli_ctx, resource_group_name)))


def _get_linux_fx_functionapp(functions_version, runtime, runtime_version):
    if runtime_version is None:
        runtime_version = FUNCTIONS_VERSION_TO_DEFAULT_RUNTIME_VERSION[functions_version][runtime]
    if runtime == 'dotnet':
        runtime_version = DOTNET_RUNTIME_VERSION_TO_DOTNET_LINUX_FX_VERSION[runtime_version]
    else:
        runtime = runtime.upper()
    return '{}|{}'.format(runtime, runtime_version)


def _get_java_version_functionapp(functions_version, runtime_version):
    if runtime_version is None:
        runtime_version = FUNCTIONS_VERSION_TO_DEFAULT_RUNTIME_VERSION[functions_version]['java']
    if runtime_version == '8':
        return '1.8'
    return runtime_version


# TODO restrict to logic apps?
def show_logicapp(cmd, resource_group_name, name):
    app = generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'get')
    if not app:
        raise ResourceNotFoundError(f"Unable to find resource '{name}', in ResourceGroup '{resource_group_name}'.")
    app.site_config = generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'get_configuration',
                                             None)
    rename_server_farm_props(app)
    fill_ftp_publishing_url(cmd, app, resource_group_name, name)
    return app


def scale_logicapp(cmd, resource_group_name, name, minimum_instance_count=None, maximum_instance_count=None, slot=None):
    return update_logicapp_scale(cmd=cmd,
                                 resource_group_name=resource_group_name,
                                 name=name,
                                 slot=slot,
                                 function_app_scale_limit=maximum_instance_count,
                                 minimum_elastic_instance_count=minimum_instance_count)


def update_logicapp_scale(cmd, resource_group_name, name, slot=None,
                          function_app_scale_limit=None,
                          minimum_elastic_instance_count=None):
    configs = get_site_configs(cmd, resource_group_name, name, slot)
    import inspect
    frame = inspect.currentframe()

    # note: getargvalues is used already in azure.cli.core.commands.
    # and no simple functional replacement for this deprecating method for 3.5
    args, _, _, values = inspect.getargvalues(frame)  # pylint: disable=deprecated-method

    for arg in args[3:]:
        if values.get(arg, None):
            setattr(configs, arg, values[arg])

    return generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'update_configuration', slot, configs)


def get_logicapp_app_settings(cmd, resource_group_name, name, slot=None):
    return get_app_settings(cmd, resource_group_name, name, slot)


def update_logicapp_app_settings(cmd, resource_group_name, name, settings=None, slot=None, slot_settings=None):
    return update_app_settings(cmd, resource_group_name, name, settings, slot, slot_settings)


def delete_logicapp_app_settings(cmd, resource_group_name, name, setting_names, slot=None):
    return delete_app_settings(cmd, resource_group_name, name, setting_names, slot)


def delete_logic_app(cmd, resource_group_name, name, slot=None):
    return generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'delete', slot)


def stop_logicapp(cmd, resource_group_name, name, slot=None):
    return generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'stop', slot)


def start_logicapp(cmd, resource_group_name, name, slot=None):
    return generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'start', slot)


def restart_logicapp(cmd, resource_group_name, name, slot=None):
    return generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'restart', slot)


def enable_zip_deploy_logicapp(cmd, resource_group_name, name, src, build_remote=False, timeout=None, slot=None):
    client = web_client_factory(cmd.cli_ctx)
    app = client.web_apps.get(resource_group_name, name)
    if app is None:
        raise ResourceNotFoundError('The function app \'{}\' was not found in resource group \'{}\'. '
                                    'Please make sure these values are correct.'.format(name, resource_group_name))
    parse_plan_id = parse_resource_id(app.server_farm_id)
    plan_info = None
    retry_delay = 10  # seconds
    # We need to retry getting the plan because sometimes if the plan is created as part of function app,
    # it can take a couple of tries before it gets the plan
    for _ in range(5):
        try:
            plan_info = client.app_service_plans.get(parse_plan_id['resource_group'],
                                                     parse_plan_id['name'])
        except:  # pylint: disable=bare-except
            pass
        if plan_info is not None:
            break
        time.sleep(retry_delay)

    is_consumption = is_plan_consumption(cmd, plan_info)
    if (not build_remote) and is_consumption and app.reserved:
        return upload_zip_to_storage(cmd, resource_group_name, name, src, slot)
    if build_remote and app.reserved:
        add_remote_build_app_settings(cmd, resource_group_name, name, slot)
    elif app.reserved:
        remove_remote_build_app_settings(cmd, resource_group_name, name, slot)

    return enable_zip_deploy(cmd, resource_group_name, name, src, timeout, slot)


def get_logicapp(cmd, resource_group_name, name, slot=None):
    app = generic_site_operation(cmd.cli_ctx, resource_group_name, name, 'get', slot)
    # TODO restrict to only logic apps; currently will get any functionapp
    if not app or 'function' not in app.kind:
        raise ResourceNotFoundError("Unable to find App {} in resource group {}".format(name, resource_group_name))
    return app


def set_logicapp(cmd, resource_group_name, name, slot=None, **kwargs):
    instance = kwargs['parameters']
    client = web_client_factory(cmd.cli_ctx)
    updater = client.web_apps.begin_create_or_update_slot if slot else client.web_apps.begin_create_or_update
    kwargs = dict(resource_group_name=resource_group_name, name=name, site_envelope=instance)
    if slot:
        kwargs['slot'] = slot

    return updater(**kwargs)


def update_logicapp(cmd, instance, plan=None, force=False):
    client = web_client_factory(cmd.cli_ctx)
    if plan is not None:
        if is_valid_resource_id(plan):
            dest_parse_result = parse_resource_id(plan)
            dest_plan_info = client.app_service_plans.get(dest_parse_result['resource_group'],
                                                          dest_parse_result['name'])
        else:
            dest_plan_info = client.app_service_plans.get(instance.resource_group, plan)
        if dest_plan_info is None:
            raise ResourceNotFoundError("The plan '{}' doesn't exist".format(plan))
        validate_plan_switch_compatibility(cmd, client, instance, dest_plan_info, force)
        instance.server_farm_id = dest_plan_info.id
    return instance
