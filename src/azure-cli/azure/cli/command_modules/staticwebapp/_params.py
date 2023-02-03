# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
# pylint: disable=line-too-long,too-many-statements

from knack.arguments import CLIArgumentType

from azure.cli.core.commands.parameters import get_location_type, get_enum_type, tags_type

from ._validators import validate_public_cloud
from ._constants import MSI_LOCAL_ID


def load_arguments(self, _):
    static_web_app_sku_arg_type = CLIArgumentType(
        help='The pricing tiers for Static Web App',
        arg_type=get_enum_type(['Free', 'Standard'])
    )

    with self.argument_context('staticwebapp', validator=validate_public_cloud) as c:
        c.argument('source', options_list=['--source', '-s'], help="URL for the repository of the static site.", arg_group="Source Control")
        c.argument('token', options_list=['--token', '-t'], arg_group="Source Control",
                   help="A user's GitHub or Azure Dev Ops repository token. This is used to create the Github Action or Dev Ops pipeline.")
        c.argument('login_with_github', help="Interactively log in with Github to retrieve the Personal Access Token", arg_group="Source Control")
        c.argument('login_with_ado', help='Use azure credentials to create an Azure Dev Ops personal access token', arg_group="Source Control")
        c.argument('branch', options_list=['--branch', '-b'], help="The target branch in the repository.", arg_group="Source Control")
        c.ignore('format_output')
        c.argument('name', options_list=['--name', '-n'], metavar='NAME', help="Name of the static site")
    with self.argument_context('staticwebapp environment') as c:
        c.argument('environment_name',
                   options_list=['--environment-name'], help="Name of the environment of static site")
    with self.argument_context('staticwebapp hostname') as c:
        c.argument('hostname',
                   options_list=['--hostname'],
                   help="custom hostname such as www.example.com. Only support sub domain in preview.")
    with self.argument_context('staticwebapp hostname set') as c:
        c.argument('validation_method',
                   options_list=['--validation-method', '-m'],
                   help="Validation method for the custom domain.",
                   arg_type=get_enum_type(["cname-delegation", "dns-txt-token"]))
    with self.argument_context('staticwebapp appsettings') as c:
        c.argument('setting_pairs', options_list=['--setting-names'],
                   help="Space-separated app settings in 'key=value' format. ",
                   nargs='*')
        c.argument('setting_names', options_list=['--setting-names'], help="Space-separated app setting names.",
                   nargs='*')
    with self.argument_context('staticwebapp users') as c:
        c.argument('authentication_provider', options_list=['--authentication-provider'],
                   help="Authentication provider of the user identity such as AAD, Facebook, GitHub, Google, Twitter.")
        c.argument('user_details', options_list=['--user-details'],
                   help="Email for AAD, Facebook, and Google. Account name (handle) for GitHub and Twitter.")
        c.argument('user_id',
                   help="Given id of registered user.")
        c.argument('domain', options_list=['--domain'],
                   help="A domain added to the static app in quotes.")
        c.argument('roles', options_list=['--roles'],
                   help="Comma-separated default or user-defined role names. "
                        "Roles that can be assigned to a user are comma separated and case-insensitive (at most 50 "
                        "roles up to 25 characters each and restricted to 0-9,A-Z,a-z, and _). "
                        "Define roles in routes.json during root directory of your GitHub repo.")
        c.argument('invitation_expiration_in_hours', options_list=['--invitation-expiration-in-hours'],
                   help="This value sets when the link will expire in hours. The maximum is 168 (7 days).")
    with self.argument_context('staticwebapp identity') as c:
        c.argument('scope', help="The scope the managed identity has access to")
        c.argument('role', help="Role name or id the managed identity will be assigned")
    with self.argument_context('staticwebapp identity assign') as c:
        c.argument('assign_identities', options_list=['--identities'], nargs='*', help=f"Space-separated identities to assign. Use '{MSI_LOCAL_ID}' to refer to the system assigned identity. Default: '{MSI_LOCAL_ID}'")
    with self.argument_context('staticwebapp identity remove') as c:
        c.argument('remove_identities', options_list=['--identities'], nargs='*', help=f"Space-separated identities to assign. Use '{MSI_LOCAL_ID}' to refer to the system assigned identity. Default: '{MSI_LOCAL_ID}'")
    with self.argument_context('staticwebapp create') as c:
        c.argument('location', arg_type=get_location_type(self.cli_ctx))
        c.argument('tags', arg_type=tags_type)
        c.argument('sku', arg_type=static_web_app_sku_arg_type)
        c.argument('app_location', options_list=['--app-location'],
                   help="Location of your application code. For example, '/' represents the root of your app, "
                        "while '/app' represents a directory called 'app'")
        c.argument('api_location', options_list=['--api-location'],
                   help="Location of your Azure Functions code. For example, '/api' represents a folder called 'api'.")
        c.argument('app_artifact_location', options_list=['--app-artifact-location'],
                   help="The path of your build output relative to your apps location. For example, setting a value "
                        "of 'build' when your app location is set to '/app' will cause the content at '/app/build' to "
                        "be served.",
                   deprecate_info=c.deprecate(expiration='2.22.1'))
        c.argument('output_location', options_list=['--output-location'],
                   help="The path of your build output relative to your apps location. For example, setting a value "
                        "of 'build' when your app location is set to '/app' will cause the content at '/app/build' to "
                        "be served.")
    with self.argument_context('staticwebapp update') as c:
        c.argument('tags', arg_type=tags_type)
        c.argument('sku', arg_type=static_web_app_sku_arg_type)
    with self.argument_context('staticwebapp functions link') as c:
        c.argument('function_resource_id', help="Resource ID of the functionapp to link. Can be retrieved with 'az functionapp --query id'")
        c.argument('environment_name', help="Name of the environment of static site")
        c.argument('force', help="Force the function link even if the function is already linked to a static webapp. May be needed if the function was previously linked to a static webapp.")
    with self.argument_context('staticwebapp backends link') as c:
        c.argument('backend_resource_id', help="Resource ID of the backend to link.")
        c.argument('backend_region', help="Region of the backend resource.")
        c.argument('environment_name', help="Name of the environment of static site")
    with self.argument_context('staticwebapp backends validate') as c:
        c.argument('backend_resource_id', help="Resource ID of the backend to link.")
        c.argument('backend_region', help="Region of the backend resource.")
        c.argument('environment_name', help="Name of the environment of static site")
    with self.argument_context('staticwebapp backends show') as c:
        c.argument('environment_name', help="Name of the environment of static site")
    with self.argument_context('staticwebapp backends unlink') as c:
        c.argument('remove_backend_auth', help="If set to true, removes the identity provider configured on the backend during the linking process.")
        c.argument('environment_name', help="Name of the environment of static site")
    with self.argument_context('staticwebapp enterprise-edge') as c:
        c.argument("no_register", help="Don't try to register the Microsoft.CDN provider. Registration can be done manually with: az provider register --wait --namespace Microsoft.CDN. For more details, please review the documentation available at https://go.microsoft.com/fwlink/?linkid=2184995 .", default=False)
