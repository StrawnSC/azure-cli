# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azure.cli.core import AzCommandsLoader

from azure.cli.command_modules.staticwebapp._help import helps  # pylint: disable=unused-import


class StaticwebappCommandsLoader(AzCommandsLoader):

    def __init__(self, cli_ctx=None):
        from azure.cli.core.commands import CliCommandType
        from azure.cli.core.profiles import ResourceType
        from azure.cli.command_modules.staticwebapp._client_factory import cf_staticwebapp
        staticwebapp_custom = CliCommandType(
            operations_tmpl='azure.cli.command_modules.staticwebapp.custom#{}',
            client_factory=cf_staticwebapp)
        super(StaticwebappCommandsLoader, self).__init__(cli_ctx=cli_ctx,
                                                         custom_command_type=staticwebapp_custom,
                                                         resource_type=ResourceType.MGMT_APPSERVICE)

    def load_command_table(self, args):
        from azure.cli.command_modules.staticwebapp.commands import load_command_table
        load_command_table(self, args)
        return self.command_table

    def load_arguments(self, command):
        from azure.cli.command_modules.staticwebapp._params import load_arguments
        load_arguments(self, command)


COMMAND_LOADER_CLS = StaticwebappCommandsLoader
