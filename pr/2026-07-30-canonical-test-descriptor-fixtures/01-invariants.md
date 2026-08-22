# Invariants

1. Tests must not accept `runtime://` descriptor references.
2. Runtime ability fixtures derive Ability URAs from the call callee and public ability name through the SDK addressing client.
3. Read abilities use read descriptor actions.
4. Product tests remain product-facing and do not hand-roll canonical descriptor parsing.

