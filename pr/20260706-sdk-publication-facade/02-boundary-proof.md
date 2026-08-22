# Boundary Proof

Correct flow:

```text
EasyRemote control facade
  -> easynet_sdk.PublicationCatalogFacade
  -> EasyRemote test identity facade
  -> SDK-shaped parse_ura/resource_ura projection
```

The test facade is only a deterministic stand-in for the SDK identity facade.
It must not preserve old helper shapes that production code is no longer
allowed to depend on.

Removed incorrect assumption:

```text
publication resource ref
  -> resource_ura(realm, owner_id, path)
```

Required assumption:

```text
publication resource ref
  -> resource_ura(owner_ura, path)
```
