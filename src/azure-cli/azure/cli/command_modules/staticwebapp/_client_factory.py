# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------


def web_client_factory(cli_ctx, api_version=None, **_):
    from azure.cli.core.profiles import ResourceType
    from azure.cli.core.commands.client_factory import get_mgmt_service_client
    return get_mgmt_service_client(cli_ctx, ResourceType.MGMT_APPSERVICE, api_version=api_version)


def providers_client_factory(cli_ctx):
    from azure.cli.core.profiles import ResourceType
    from azure.cli.core.commands.client_factory import get_mgmt_service_client
    return get_mgmt_service_client(cli_ctx, ResourceType.MGMT_RESOURCE_RESOURCES).providers


def cf_staticwebapp(cli_ctx, _):
    return web_client_factory(cli_ctx).static_sites


def cf_plans(cli_ctx, _):
    return web_client_factory(cli_ctx).app_service_plans


def cf_webapps(cli_ctx, _):
    return web_client_factory(cli_ctx).web_apps


def cf_providers(cli_ctx, _):
    return web_client_factory(cli_ctx).provider  # pylint: disable=no-member


def cf_web_client(cli_ctx, _):
    return web_client_factory(cli_ctx)
