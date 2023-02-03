# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from knack.help_files import helps  # pylint: disable=unused-import


helps['staticwebapp'] = """
    type: group
    short-summary: Manage static apps.
"""

helps['staticwebapp list'] = """
    type: command
    short-summary: List all static app resources in a subscription, or in resource group if provided
    examples:
    - name: List static apps in a subscription.
      text: az staticwebapp list
"""

helps['staticwebapp show'] = """
    type: command
    short-summary: Show details of a static app.
    examples:
    - name: Show static app in a subscription.
      text: az staticwebapp show -n MyStaticAppName
"""

helps['staticwebapp create'] = """
    type: command
    short-summary: Create a static app. To provide content to the static web app and integrate with a Github repo, provide the Github repository URL (--source) and a branch (--branch). If the repo is under a Github organization, please ensure that the Azure CLI Github App has access to the organization. Access can be requested in the browser when using the "--login-with-github" argument. Access must be granted by the organization's admin.
    examples:
    - name: Create static app in a subscription.
      text: az staticwebapp create -n MyStaticAppName -g MyExistingRg
       -s https://github.com/JohnDoe/my-first-static-web-app -l WestUs2 -b master -t MyAccessToken
    - name: Create static app in a subscription, retrieving token interactively
      text: az staticwebapp create -n MyStaticAppName -g MyExistingRg
       -s https://github.com/JohnDoe/my-first-static-web-app -l WestUs2 -b master --login-with-github
    - name: Create a static web app without any content and without a github integration
      text: az staticwebapp create -n MyStaticAppName -g MyExistingRg
"""

helps['staticwebapp update'] = """
    type: command
    short-summary: Update a static app. Return the app updated.
    examples:
    - name: Update static app to standard sku.
      text: az staticwebapp update -n MyStaticAppName --sku Standard
"""

helps['staticwebapp disconnect'] = """
    type: command
    short-summary: Disconnect source control to enable connecting to a different repo.
    examples:
    - name: Disconnect static app.
      text: az staticwebapp disconnect -n MyStaticAppName
"""

helps['staticwebapp reconnect'] = """
    type: command
    short-summary: Connect to a repo and branch following a disconnect command.
    examples:
    - name: Connect a repo and branch to static app.
      text: az staticwebapp reconnect -n MyStaticAppName --source MyGitHubRepo -b master --token MyAccessToken
    - name: Connect a repo and branch to static app, retrieving token interactively
      text: az staticwebapp reconnect -n MyStaticAppName --source MyGitHubRepo -b master --login-with-github
"""

helps['staticwebapp delete'] = """
    type: command
    short-summary: Delete a static app.
    examples:
    - name: Delete a static app.
      text: az staticwebapp delete -n MyStaticAppName -g MyRg
"""

helps['staticwebapp environment'] = """
    type: group
    short-summary: Manage environment of the static app.
"""

helps['staticwebapp environment list'] = """
    type: command
    short-summary: List all environment of the static app including production.
    examples:
    - name: List static app environment.
      text: az staticwebapp environment list -n MyStaticAppName
"""

helps['staticwebapp environment show'] = """
    type: command
    short-summary: Show information about the production environment or the specified environment.
    examples:
    - name: Show a static app environment.
      text: az staticwebapp environment show -n MyStaticAppName
"""

helps['staticwebapp environment delete'] = """
    type: command
    short-summary: Delete the static app production environment or the specified environment.
    examples:
    - name: Delete a static app environment.
      text: az staticwebapp environment delete -n MyStaticAppName
"""

helps['staticwebapp environment functions'] = """
    type: command
    short-summary: Show information about functions.
    examples:
    - name: Show static app functions.
      text: az staticwebapp environment functions -n MyStaticAppName
"""

helps['staticwebapp hostname'] = """
    type: group
    short-summary: Manage custom hostnames of Functions of the static app.
"""

helps['staticwebapp hostname list'] = """
    type: command
    short-summary: List custom hostnames of the static app.
    examples:
    - name: List custom hostnames of the static app.
      text: az staticwebapp hostname list -n MyStaticAppName
"""

helps['staticwebapp hostname set'] = """
    type: command
    short-summary: Set given sub-domain hostname to the static app. Please configure CNAME/TXT/ALIAS record with your DNS provider. Use --no-wait to not wait for validation.
    examples:
    - name: Set a hostname for a static app using CNAME validation (default)
      text: az staticwebapp hostname set -n MyStaticAppName --hostname www.example.com
    - name: Set a root domain for a webapp using TXT validation
      text: az staticwebapp hostname set -n MyStaticAppName --hostname example.com --validation-method "dns-txt-token"
"""

helps['staticwebapp hostname show'] = """
    type: command
    short-summary: Get details for a staticwebapp custom domain. Can be used to fetch validation token for TXT domain validation (see example).
    examples:
    - name: Fetch the validation token (if generated) for TXT validation
      text: az staticwebapp hostname show -n MyStaticAppName -g MyResourceGroup --hostname example.com --query "validationToken"
    - name: Show all custom domain details for a particular hostname
      text: az staticwebapp hostname show -n MyStaticAppName -g MyResourceGroup --hostname example.com
"""

helps['staticwebapp hostname delete'] = """
    type: command
    short-summary: Delete given hostname of the static app.
    examples:
    - name: Delete given hostname of the static app.
      text: az staticwebapp hostname delete -n MyStaticAppName --hostname HostnameToDelete
"""

helps['staticwebapp appsettings'] = """
    type: group
    short-summary: Manage app settings the static app.
"""

helps['staticwebapp appsettings list'] = """
    type: command
    short-summary: List app settings of the static app.
    examples:
    - name: List app settings of the static app.
      text: az staticwebapp appsettings list -n MyStaticAppName
"""

helps['staticwebapp appsettings set'] = """
    type: command
    short-summary: Add to or change the app settings of the static app.
    examples:
    - name: Add to or change the app settings of the static app.
      text: az staticwebapp appsettings set -n MyStaticAppName --setting-names key1=val1 key2=val2
"""

helps['staticwebapp appsettings delete'] = """
    type: command
    short-summary: Delete app settings with given keys of the static app.
    examples:
    - name: Delete given app settings of the static app.
      text: az staticwebapp appsettings delete -n MyStaticAppName --setting-names key1 key2
"""

helps['staticwebapp identity'] = """
type: group
short-summary: Manage a static web app's managed identity
"""

helps['staticwebapp identity assign'] = """
type: command
short-summary: assign managed identity to the static web app
examples:
  - name: assign local identity and assign a reader role to the current resource group.
    text: >
        az staticwebapp identity assign -g MyResourceGroup -n MyUniqueApp --role reader --scope /subscriptions/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/resourcegroups/MyResourceGroup
  - name: enable identity for the web app.
    text: >
        az staticwebapp identity assign -g MyResourceGroup -n MyUniqueApp
  - name: assign local identity and a user assigned identity to a static web app.
    text: >
        az staticwebapp identity assign -g MyResourceGroup -n MyUniqueApp --identities [system] myAssignedId
"""

helps['staticwebapp identity remove'] = """
type: command
short-summary: Disable static web app's managed identity
examples:
  - name: Disable static web app's system managed identity
    text: az staticwebapp identity remove --name MyApp --resource-group MyResourceGroup
    crafted: true
  - name: Disable static web app's system managed identity and a user managed identity
    text: az staticwebapp identity remove --name MyApp --resource-group MyResourceGroup --identities [system] myAssignedId
"""

helps['staticwebapp identity show'] = """
type: command
short-summary: display static web app's managed identity
examples:
  - name: display static web app's managed identity (autogenerated)
    text: az staticwebapp identity show --name MyApp --resource-group MyResourceGroup
    crafted: true
"""

helps['staticwebapp users'] = """
    type: group
    short-summary: Manage users of the static app.
"""

helps['staticwebapp users list'] = """
    type: command
    short-summary: Lists users and assigned roles, limited to users who accepted their invites.
    examples:
    - name: Lists users and assigned roles.
      text: az staticwebapp users list -n MyStaticAppName
"""

helps['staticwebapp users invite'] = """
    type: command
    short-summary: Create invitation link for specified user to the static app.
    examples:
    - name: Create invitation link for specified user to the static app.
      text: az staticwebapp users invite -n MyStaticAppName --authentication-provider GitHub --user-details JohnDoe
       --role Contributor --domain static-app-001.azurestaticapps.net --invitation-expiration-in-hours 1

"""

helps['staticwebapp users update'] = """
    type: command
    short-summary: Updates a user entry with the listed roles. Either user details or user id is required.
    examples:
    - name: Updates a user entry with the listed roles.
      text: az staticwebapp users update -n MyStaticAppName --user-details JohnDoe --role Contributor
"""

helps['staticwebapp secrets'] = """
    type: group
    short-summary: Manage deployment token for the static app
"""

helps['staticwebapp secrets list'] = """
    type: command
    short-summary: List the deployment token for the static app.
    examples:
    - name: List deployment token
      text: az staticwebapp secrets list --name MyStaticAppName
"""

helps['staticwebapp secrets reset-api-key'] = """
    type: command
    short-summary: Reset the deployment token for the static app.
    examples:
    - name: Reset deployment token
      text: az staticwebapp secrets reset-api-key --name MyStaticAppName
"""

helps['staticwebapp functions'] = """
type: group
short-summary: Link or unlink a prexisting functionapp with a static webapp. Also known as "Bring your own Functions."
"""

helps['staticwebapp functions link'] = """
    type: command
    short-summary: Link an Azure Function to a static webapp. Also known as "Bring your own Functions." Only one Azure Functions app is available to a single static web app. Static webapp SKU must be "Standard"
    examples:
    - name: Link a function to a static webapp
      text: az staticwebapp functions link -n MyStaticAppName -g MyResourceGroup --function-resource-id "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Web/sites/<function-name>"
"""

helps['staticwebapp functions unlink'] = """
    type: command
    short-summary: Unlink an Azure Function from a static webapp
    examples:
    - name: Show static app functions.
      text: az staticwebapp functions unlink -n MyStaticAppName -g MyResourceGroup
"""

helps['staticwebapp functions show'] = """
    type: command
    short-summary: Show details on the Azure Function linked to a static webapp
    examples:
    - name: Show static app functions.
      text: az staticwebapp functions show -n MyStaticAppName -g MyResourceGroup
"""

helps['staticwebapp backends'] = """
type: group
short-summary: Link or unlink a prexisting backend with a static web app. Also known as "Bring your own API."
"""

helps['staticwebapp backends validate'] = """
    type: command
    short-summary: Validate a backend for a static web app
    long-summary: >
      Only one backend is available to a single static web app.
      If a backend was previously linked to another static Web App, the auth configuration must first be removed from the backend before linking to a different Static Web App.
      Static web app SKU must be "Standard".
      Supported backend types are Azure Functions, Azure API Management, Azure App Service, Azure Container Apps.
      Backend region must be provided for backends of type Azure Functions and Azure App Service.
      See https://learn.microsoft.com/azure/static-web-apps/apis-overview to learn more.
    examples:
    - name: Validate a backend for a static web app
      text: az staticwebapp backends validate -n MyStaticAppName -g MyResourceGroup --backend-resource-id "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/<resource-provider>/<resource-type>/<backend-name>" --backend-region MyBackendRegion
    - name: Validate a backend for a static web app environment
      text: az staticwebapp backends validate -n MyStaticAppName -g MyResourceGroup --environment-name MyEnvironmentName --backend-resource-id "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/<resource-provider>/<resource-type>/<backend-name>" --backend-region MyBackendRegion
"""

helps['staticwebapp backends link'] = """
    type: command
    short-summary: Link a backend to a static web app. Also known as "Bring your own API."
    long-summary: >
      Only one backend is available to a single static web app.
      If a backend was previously linked to another static Web App, the auth configuration must first be removed from the backend before linking to a different Static Web App.
      Static web app SKU must be "Standard".
      Supported backend types are Azure Functions, Azure API Management, Azure App Service, Azure Container Apps.
      Backend region must be provided for backends of type Azure Functions and Azure App Service.
      See https://learn.microsoft.com/azure/static-web-apps/apis-overview to learn more.
    examples:
    - name: Link a backend to a static web app
      text: az staticwebapp backends link -n MyStaticAppName -g MyResourceGroup --backend-resource-id "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/<resource-provider>/<resource-type>/<backend-name>" --backend-region MyBackendRegion
    - name: Link a backend to a static web app environment
      text: az staticwebapp backends link -n MyStaticAppName -g MyResourceGroup --environment-name MyEnvironmentName --backend-resource-id "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/<resource-provider>/<resource-type>/<backend-name>" --backend-region MyBackendRegion
"""

helps['staticwebapp backends unlink'] = """
    type: command
    short-summary: Unlink backend from a static web app
    examples:
    - name: Unlink static app backends.
      text: az staticwebapp backends unlink -n MyStaticAppName -g MyResourceGroup
    - name: Unlink backend from static web app environment and remove auth config from backend.
      text: az staticwebapp backends unlink -n MyStaticAppName -g MyResourceGroup --environment-name MyEnvironmentName --remove-backend-auth
"""

helps['staticwebapp backends show'] = """
    type: command
    short-summary: Show details on the backend linked to a static web app
    examples:
    - name: Show static web app backends.
      text: az staticwebapp backends show -n MyStaticAppName -g MyResourceGroup
    - name: Show static web app backends for environment.
      text: az staticwebapp backends show -n MyStaticAppName -g MyResourceGroup --environment-name MyEnvironmentName
"""

helps['staticwebapp enterprise-edge'] = """
    type: group
    short-summary: Manage the Azure Front Door CDN for static webapps. For optimal experience and availability please check our documentation https://aka.ms/swaedge
"""

helps['staticwebapp enterprise-edge enable'] = """
    type: command
    short-summary: Enable the Azure Front Door CDN for a static webapp. Enabling enterprise-grade edge requires re-registration for the Azure Front Door Microsoft.CDN resource provider. For optimal experience and availability please check our documentation https://aka.ms/swaedge
"""

helps['staticwebapp enterprise-edge disable'] = """
    type: command
    short-summary: Disable the Azure Front Door CDN for a static webapp. For optimal experience and availability please check our documentation https://aka.ms/swaedge
"""

helps['staticwebapp enterprise-edge show'] = """
    type: command
    short-summary: Show the status (Enabled, Disabled, Enabling, Disabling) of the Azure Front Door CDN for a webapp. For optimal experience and availability please check our documentation https://aka.ms/swaedge
"""
