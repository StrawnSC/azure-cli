# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azure.cli.core.azclierror import ValidationError, RequiredArgumentMissingError, ResourceNotFoundError

from ._constants import MSI_LOCAL_ID
from ._client_factory import cf_webapps


def normalize_sku_for_staticapp(sku):
    if sku.lower() == 'free':
        return 'Free'
    if sku.lower() == 'standard':
        return 'Standard'
    raise ValidationError("Invalid sku(pricing tier), please refer to command help for valid values")


def raise_missing_token_suggestion():
    pat_documentation = "https://help.github.com/en/articles/creating-a-personal-access-token-for-the-command-line"
    raise RequiredArgumentMissingError("GitHub access token is required to authenticate to your repositories. "
                                       "If you need to create a Github Personal Access Token, "
                                       "please run with the '--login-with-github' flag or follow "
                                       "the steps found at the following link:\n{0}".format(pat_documentation))


def raise_missing_ado_token_suggestion():
    pat_documentation = ("https://learn.microsoft.com/en-us/azure/devops/organizations/accounts/use-personal-access-"
                         "tokens-to-authenticate?view=azure-devops&tabs=Windows#create-a-pat")
    raise RequiredArgumentMissingError("If this repo is an Azure Dev Ops repo, please provide a Personal Access Token."
                                       "Please run with the '--login-with-ado' flag or follow "
                                       "the steps found at the following link:\n{0}".format(pat_documentation))


def build_identities_info(identities):
    identities = identities or []
    identity_types = []
    if not identities or MSI_LOCAL_ID in identities:
        identity_types.append('SystemAssigned')
    external_identities = [x for x in identities if x != MSI_LOCAL_ID]
    if external_identities:
        identity_types.append('UserAssigned')
    identity_types = ','.join(identity_types)
    info = {'type': identity_types}
    if external_identities:
        info['userAssignedIdentities'] = {e: {} for e in external_identities}
    return (info, identity_types, external_identities, 'SystemAssigned' in identity_types)


# TODO test
def get_appservice_app(cmd, resource_group_name, name):
    client = cf_webapps(cmd.cli_ctx)
    app = client.get(resource_group_name=resource_group_name, name=name)
    if not app:
        raise ResourceNotFoundError("Unable to find resource '{}', in ResourceGroup '{}'.".format(name,
                                                                                                  resource_group_name))
    return app
