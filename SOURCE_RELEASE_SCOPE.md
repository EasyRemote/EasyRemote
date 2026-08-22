# Public Source Release Scope

EasyRemote is the public Python facade for a wider EasyNet system that is
released in stages. The package, examples, and implementation files present in
this repository are public so that developers can build integrations, reproduce
behavior, and examine the advertised interface. Their publication does not mean
that every hosted control-plane service, production deployment component,
research prototype, or evaluation asset in the wider system has been released.

The staged boundary serves four practical purposes.

## Independent provenance

Tagged source releases create an auditable record of the interface and its
authorship. Holding back unstable implementation mechanisms until they are
ready for review reduces the risk that early research is absorbed elsewhere
without clear attribution while still establishing public priority for the
interfaces being evaluated.

## Sustainable maintenance

Every public surface creates a long-lived compatibility and support obligation.
The project therefore opens bounded, testable interfaces rather than turning
each research iteration into many indefinite environment, deployment, and
legacy-platform commitments. This keeps maintenance proportional to the
available research capacity.

## Peer-review integrity

Unpublished mechanisms, evaluation harnesses, and experiment details may remain
private while peer review is in progress where a venue's anonymity or prior-
disclosure policy requires it. Release decisions follow the policy applicable
to the work rather than assuming one rule for every venue.

## Deployment readiness

Additional implementation layers are released when real production agentic
workflows can exercise their security, recovery, and operational contracts.
Prematurely publishing an unsupported control plane would create adoption and
maintenance signals that do not yet test the research question.

## License boundary

MIT applies to the files and artifacts that are actually distributed under that
license. This scope statement adds no restriction to those rights. Components
or materials that are not present in a public distribution are not implicitly
licensed by the existence of this repository.
