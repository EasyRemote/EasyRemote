# Intent

Remove process-cwd coupling from EasyRemote ability installation. A client must
not mint `fs/workspace` ResourceRefs by assuming its cwd is the daemon's
workspace. Materialize the bundle through the selected Device's canonical
`fs.transfer` ability before invoking `ability.deploy`.
