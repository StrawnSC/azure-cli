# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

# pylint: disable=line-too-long
from azure.cli.core.commands import CliCommandType
from azure.cli.command_modules.logicapp._client_factory import cf_webapps
from azure.cli.core.util import empty_on_404


def ex_handler_factory():
    def _ex_handler(ex):
        ex = _polish_bad_errors(ex)
        raise ex
    return _ex_handler


def _polish_bad_errors(ex):
    import json
    from knack.util import CLIError
    try:
        if hasattr(ex, "response"):
            if 'text/plain' in ex.response.headers['Content-Type']:  # HTML Response
                detail = ex.response.text
            else:
                detail = json.loads(ex.response.text())['Message']
        else:
            detail = json.loads(ex.error_msg.response.text())['Message']
        ex = CLIError(detail)
    except Exception:  # pylint: disable=broad-except
        pass
    return ex


def update_function_ex_handler_factory():
    from azure.cli.core.azclierror import ClientRequestError

    def _ex_handler(ex):
        http_error_response = False
        if hasattr(ex, 'response'):
            http_error_response = True
        ex = _polish_bad_errors(ex, False)
        # only include if an update was attempted and failed on the backend
        if http_error_response:
            try:
                detail = ('If using \'--plan\', a consumption plan may be unable to migrate '
                          'to a given premium plan. Please confirm that the premium plan '
                          'exists in the same resource group and region. Note: Not all '
                          'functionapp plans support premium instances. If you have verified '
                          'your resource group and region and are still unable to migrate, '
                          'please redeploy on a premium functionapp plan.')
                ex = ClientRequestError(ex.args[0] + '\n\n' + detail)
            except Exception:  # pylint: disable=broad-except
                pass
        raise ex
    return _ex_handler


def transform_web_output(web):
    props = ['name', 'state', 'location', 'resourceGroup', 'defaultHostName', 'appServicePlanId', 'ftpPublishingUrl']
    result = {k: web[k] for k in web if k in props}
    # to get width under control, also the plan usually is in the same RG
    result['appServicePlan'] = result.pop('appServicePlanId').split('/')[-1]
    return result


def transform_web_list_output(webs):
    return [transform_web_output(w) for w in webs]


def load_command_table(self, _):
    logicapp_custom = CliCommandType(operations_tmpl='azure.cli.command_modules.logicapp.custom#{}',
                                     client_factory=cf_webapps)

    with self.command_group('logicapp', custom_command_type=logicapp_custom) as g:
        g.custom_command('create', 'create_logicapp', exception_handler=ex_handler_factory())
        g.custom_command('list', 'list_logicapp', table_transformer=transform_web_list_output)
        g.custom_show_command('show', 'show_logicapp', table_transformer=transform_web_output)
        g.custom_command('scale', 'scale_logicapp', exception_handler=ex_handler_factory())
        g.custom_command('delete', 'delete_logic_app', confirmation=True)
        g.custom_command('stop', 'stop_logicapp')
        g.custom_command('start', 'start_logicapp')
        g.custom_command('restart', 'restart_logicapp')
        g.generic_update_command('update', getter_name="get_logicapp", setter_name='set_logicapp', exception_handler=update_function_ex_handler_factory(),
                                 custom_func_name='update_logicapp', getter_type=logicapp_custom, setter_type=logicapp_custom, command_type=logicapp_custom)

    with self.command_group('logicapp config appsettings', custom_command_type=logicapp_custom) as g:
        g.custom_command('list', 'get_logicapp_app_settings', exception_handler=empty_on_404)
        g.custom_command('set', 'update_logicapp_app_settings', exception_handler=ex_handler_factory())
        g.custom_command('delete', 'delete_logicapp_app_settings', exception_handler=ex_handler_factory())

    with self.command_group('logicapp deployment source') as g:
        g.custom_command('config-zip', 'enable_zip_deploy_logicapp')
