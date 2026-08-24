# Boundary proof

`easyremote._ability_staging` owns product-level archive and upload
orchestration. `easynet_sdk.RuntimeAbilityClient` still owns descriptor
resolution, authority binding, bidi sequencing, and receipt verification. The
target locomotion SystemAgent owns `fs.transfer`; the target
ability-management SystemAgent owns `ability.deploy`. No raw host path crosses
the Invocation boundary and no workspace root is inferred outside the daemon.
