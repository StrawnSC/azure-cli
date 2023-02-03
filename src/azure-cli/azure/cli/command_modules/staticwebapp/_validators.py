# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------


from azure.cli.core.azclierror import ArgumentUsageError, ValidationError
from azure.cli.core.commands.client_factory import get_mgmt_service_client

from msrestazure.tools import is_valid_resource_id


def validate_staticsite_sku(cmd, namespace):
    from azure.mgmt.web import WebSiteManagementClient
    client = get_mgmt_service_client(cmd.cli_ctx, WebSiteManagementClient).static_sites
    sku_name = client.get_static_site(namespace.resource_group_name, namespace.name).sku.name
    if sku_name.lower() != "standard":
        raise ValidationError("Invalid SKU: '{}'. Staticwebapp must have 'Standard' SKU".format(sku_name))


def validate_staticsite_link_function(cmd, namespace):
    from azure.mgmt.web import WebSiteManagementClient
    validate_staticsite_sku(cmd, namespace)

    if not is_valid_resource_id(namespace.function_resource_id):
        raise ArgumentUsageError("--function-resource-id must specify a function resource ID. "
                                 "To get resource ID, use the following commmand, inserting the function "
                                 "group/name as needed: \n"
                                 "az functionapp show --resource-group \"[FUNCTION_RESOURCE_GROUP]\" "
                                 "--name \"[FUNCTION_NAME]\" --query id ")

    client = get_mgmt_service_client(cmd.cli_ctx, WebSiteManagementClient, api_version="2020-12-01").static_sites
    functions = client.get_user_provided_function_apps_for_static_site(
        name=namespace.name, resource_group_name=namespace.resource_group_name)
    if list(functions):
        raise ValidationError("Cannot have more than one user provided function app associated with a Static Web App")


def validate_public_cloud(cmd):
    from azure.cli.core.cloud import AZURE_PUBLIC_CLOUD
    if cmd.cli_ctx.cloud.name != AZURE_PUBLIC_CLOUD.name:
        raise ValidationError('This command is not yet supported on soveriegn clouds.')
