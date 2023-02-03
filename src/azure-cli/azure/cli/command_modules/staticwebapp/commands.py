# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

# pylint: disable=line-too-long
from azure.cli.core.commands import CliCommandType
from ._validators import validate_staticsite_link_function, validate_staticsite_sku


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


def load_command_table(self, _):
    staticsite_sdk = CliCommandType(operations_tmpl='azure.cli.command_modules.staticwebapp.custom#{}')

    with self.command_group('staticwebapp', custom_command_type=staticsite_sdk) as g:
        g.custom_command('list', 'list_staticsites')
        g.custom_show_command('show', 'show_staticsite')
        g.custom_command('create', 'create_staticsites', supports_no_wait=True, exception_handler=ex_handler_factory())
        g.custom_command('delete', 'delete_staticsite', supports_no_wait=True, confirmation=True)
        g.custom_command('disconnect', 'disconnect_staticsite', supports_no_wait=True)
        g.custom_command('reconnect', 'reconnect_staticsite', supports_no_wait=True)
        g.custom_command('update', 'update_staticsite', supports_no_wait=True)

    with self.command_group('staticwebapp environment', custom_command_type=staticsite_sdk) as g:
        g.custom_command('list', 'list_staticsite_environments')
        g.custom_show_command('show', 'show_staticsite_environment')
        g.custom_command('functions', 'list_staticsite_functions')
        g.custom_command('delete', 'delete_staticsite_environment', confirmation=True)

    with self.command_group('staticwebapp hostname', custom_command_type=staticsite_sdk) as g:
        g.custom_command('list', 'list_staticsite_domains')
        g.custom_command('set', 'set_staticsite_domain', supports_no_wait=True, exception_handler=ex_handler_factory())
        g.custom_command('delete', 'delete_staticsite_domain', supports_no_wait=True, confirmation=True)
        g.custom_show_command('show', 'get_staticsite_domain')

    with self.command_group('staticwebapp identity', custom_command_type=staticsite_sdk) as g:
        g.custom_command('assign', 'assign_identity', exception_handler=ex_handler_factory())
        g.custom_command('remove', 'remove_identity', confirmation=True)
        g.custom_show_command('show', 'show_identity')

    with self.command_group('staticwebapp appsettings', custom_command_type=staticsite_sdk) as g:
        g.custom_command('list', 'list_staticsite_app_settings')
        g.custom_command('set', 'set_staticsite_app_settings')
        g.custom_command('delete', 'delete_staticsite_app_settings')

    with self.command_group('staticwebapp users', custom_command_type=staticsite_sdk) as g:
        g.custom_command('list', 'list_staticsite_users')
        g.custom_command('invite', 'invite_staticsite_users')
        g.custom_command('update', 'update_staticsite_users')

    with self.command_group('staticwebapp secrets', custom_command_type=staticsite_sdk) as g:
        g.custom_command('list', 'list_staticsite_secrets')
        g.custom_command('reset-api-key', 'reset_staticsite_api_key', supports_no_wait=True)

    with self.command_group('staticwebapp functions', custom_command_type=staticsite_sdk) as g:
        g.custom_command('link', 'link_user_function', validator=validate_staticsite_link_function)
        g.custom_command('unlink', 'unlink_user_function', validator=validate_staticsite_sku)
        g.custom_show_command('show', 'get_user_function', validator=validate_staticsite_sku)

    with self.command_group('staticwebapp backends', custom_command_type=staticsite_sdk) as g:
        g.custom_command('validate', 'validate_backend', validator=validate_staticsite_sku, exception_handler=ex_handler_factory())
        g.custom_command('link', 'link_backend', validator=validate_staticsite_sku, exception_handler=ex_handler_factory())
        g.custom_command('unlink', 'unlink_backend', validator=validate_staticsite_sku, exception_handler=ex_handler_factory())
        g.custom_show_command('show', 'get_backend', validator=validate_staticsite_sku)

    with self.command_group('staticwebapp enterprise-edge', custom_command_type=staticsite_sdk) as g:
        g.custom_command('enable', 'enable_staticwebapp_enterprise_edge')
        g.custom_command('disable', 'disable_staticwebapp_enterprise_edge')
        g.custom_show_command('show', 'show_staticwebapp_enterprise_edge_status')
