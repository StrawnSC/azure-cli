# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
# pylint: disable=line-too-long

from knack.arguments import CLIArgumentType

from azure.cli.core.local_context import LocalContextAttribute, LocalContextAction
from azure.cli.core.commands.parameters import (get_resource_name_completion_list,
                                                get_three_state_flag, get_enum_type, tags_type)
from ._constants import OS_TYPES
from ._validators import validate_timeout_value


def load_arguments(self, _):
    logicapp_name_arg_type = CLIArgumentType(options_list=['--name', '-n'], metavar='NAME',
                                             help="name of the logic app.",
                                             local_context_attribute=LocalContextAttribute(name='logicapp_name',
                                                                                           actions=[LocalContextAction.GET]))

    with self.argument_context("logicapp") as c:
        c.ignore('app_instance')
        c.argument('name', arg_type=logicapp_name_arg_type, id_part='name', help='name of the Logic App')
        c.argument('slot', options_list=['--slot', '-s'],
                   help="the name of the slot. Default to the productions slot if not specified")

    with self.argument_context('logicapp create') as c:
        c.argument('deployment_container_image_name', options_list=['--deployment-container-image-name', '-i'],
                   help='Container image name from Docker Hub, e.g. publisher/image-name:tag')
        c.argument('deployment_local_git', action='store_true', options_list=['--deployment-local-git', '-l'],
                   help='enable local git')
        c.argument('deployment_zip', options_list=['--deployment-zip', '-z'],
                   help='perform deployment using zip file')
        c.argument('deployment_source_url', options_list=['--deployment-source-url', '-u'],
                   help='Git repository URL to link with manual integration')
        c.argument('deployment_source_branch', options_list=['--deployment-source-branch', '-b'],
                   help='the branch to deploy')
        c.argument('tags', arg_type=tags_type)
        c.argument('https_only', help="Redirect all traffic made to an app using HTTP to HTTPS.",
                   arg_type=get_three_state_flag())
        c.argument('plan', options_list=['--plan', '-p'], configured_default='appserviceplan',
                   completer=get_resource_name_completion_list('Microsoft.Web/serverFarms'),
                   help="name or resource id of the Logic App app service plan. Use 'appservice plan create' to get one. If using an App Service plan from a different resource group, the full resource id must be used and not the plan name.",
                   local_context_attribute=LocalContextAttribute(name='plan_name', actions=[LocalContextAction.GET]))
        c.argument('name', options_list=['--name', '-n'], help='name of the new Logic App',
                   local_context_attribute=LocalContextAttribute(name='logicapp_name', actions=[LocalContextAction.SET], scopes=["logicapp"]))
        c.argument('storage_account', options_list=['--storage-account', '-s'],
                   help='Provide a string value of a Storage Account in the provided Resource Group. Or Resource ID of a Storage Account in a different Resource Group',
                   local_context_attribute=LocalContextAttribute(name='storage_account_name', actions=[LocalContextAction.GET]))
        c.argument('consumption_plan_location', options_list=['--consumption-plan-location', '-c'],
                   help="Geographic location where Logic App will be hosted. Use `az logicapp list-consumption-locations` to view available locations.")  # TODO add location param type?
        c.argument('os_type', arg_type=get_enum_type(OS_TYPES), help="Set the OS type for the app to be created.")
        c.argument('app_insights_key', help="Instrumentation key of App Insights to be added.")
        c.argument('app_insights',
                   help="Name of the existing App Insights project to be added to the Logic App. Must be in the "
                        "same resource group.")
        c.argument('disable_app_insights', arg_type=get_three_state_flag(return_label=True),
                   help="Disable creating application insights resource during Logic App create. No logs will be available.")
        c.argument('docker_registry_server_user', options_list=['--docker-registry-server-user', '-d'], help='The container registry server username.')
        c.argument('docker_registry_server_password', options_list=['--docker-registry-server-password', '-w'],
                   help='The container registry server password. Required for private registries.')

    with self.argument_context('logicapp') as c:
        c.argument('name', arg_type=logicapp_name_arg_type)

    with self.argument_context('logicapp show') as c:
        c.argument('name', arg_type=logicapp_name_arg_type)

    with self.argument_context('logicapp delete') as c:
        c.argument('name', arg_type=logicapp_name_arg_type, local_context_attribute=None)

    with self.argument_context('logicapp update') as c:
        c.argument('plan', help='The name or resource id of the plan to update the logicapp with.')
        c.ignore('force')

    with self.argument_context('logicapp deployment source config-zip') as c:
        c.argument('src', help='a zip file path for deployment')
        c.argument('build_remote', help='enable remote build during deployment',
                   arg_type=get_three_state_flag(return_label=True))
        c.argument('timeout', type=int, options_list=['--timeout', '-t'],
                   help='Configurable timeout in seconds for checking the status of deployment',
                   validator=validate_timeout_value)

    with self.argument_context('logicapp config appsettings') as c:
        c.argument('settings', nargs='+', help="space-separated app settings in a format of `<name>=<value>`")
        c.argument('setting_names', nargs='+', help="space-separated app setting names")
        c.argument('slot_settings', nargs='+', help="space-separated slot app settings in a format of `<name>=<value>`")

    with self.argument_context('logicapp config appsettings list') as c:
        c.argument('name', arg_type=logicapp_name_arg_type, id_part=None)

    with self.argument_context('logicapp scale') as c:
        c.argument('minimum_instance_count', options_list=['--min-instances'], type=int,
                   help='The number of instances that are always ready and warm for this logic app.')
        c.argument('maximum_instance_count', options_list=['--max-instances'], type=int,
                   help='The maximum number of instances this logic app can scale out to under load.')
