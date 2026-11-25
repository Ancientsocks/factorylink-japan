# Local workspace onboarding

## Create a workspace

Use the sign-in screen's workspace registration link or send a POST request to `/api/v1/organizations/register`. Manufacturer workspaces receive an initial `ORG_ADMIN`; supplier workspaces receive an initial `SUPPLIER_USER`. Passwords must be at least 12 characters.

## Link a supplier workspace

1. The supplier registers its own workspace.
2. The supplier shares its company code with the factory through a trusted channel.
3. A factory administrator or production manager creates a supplier directory record and sets `supplier_organization_code` to that code.
4. Future purchase orders for the linked directory record are visible to users belonging to that supplier organisation.

Company codes are not passwords. Do not publish them broadly. Public registration is not rate-limited in this local release and must be protected before internet exposure.
