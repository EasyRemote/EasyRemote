# References

Author: Silan Hu (silan.hu@u.nus.edu)

This file lists the systems papers, standards, and protocols that inform
EasyRemote's design positioning. These are references for the product and
research narrative; they are not code dependencies unless explicitly listed in
`NOTICE.md`.

## EasyNet Runtime Stack

1. EasyNet-Axon. Protocol layer used by EasyRemote for URA parsing/building and
   invocation/receipt semantics. Apache-2.0.
   https://github.com/EasyRemote/EasyNet-Axon
2. EasyNet-Cli. Local daemon, ability deployment, and `libeasynet_cli` C ABI
   runtime used by EasyRemote. Apache-2.0.
   https://github.com/EasyRemote/EasyNet-Cli
3. EasyNet. Backend/runtime family referenced by the EasyNet stack. Apache-2.0.
   https://github.com/EasyRemote/EasyNet

## Capability And Authority

4. Mark S. Miller, Ka-Ping Yee, Jonathan Shapiro. "Capability Myths
   Demolished." Johns Hopkins University Systems Research Laboratory, 2003.
   https://papers.agoric.com/assets/pdf/papers/capability-myths-demolished.pdf
5. Arnar Birgisson, Joe Gibbs Politz, Ulfar Erlingsson, Ankur Taly, Michael
   Vrable. "Macaroons: Cookies with Contextual Caveats for Decentralized
   Authorization in the Cloud." NDSS 2014.
   https://www.ndss-symposium.org/ndss2014/ndss-2014-programme/macaroons-cookies-contextual-caveats-decentralized-authorization-cloud/

## Distributed Execution And Orchestration Context

6. Philipp Moritz, Robert Nishihara, Stephanie Wang, Alexey Tumanov, Richard
   Liaw, Eric Liang, Melih Elibol, Zongheng Yang, William Paul, Michael I.
   Jordan, Ion Stoica. "Ray: A Distributed Framework for Emerging AI
   Applications." OSDI 2018.
   https://www.usenix.org/conference/osdi18/presentation/moritz
7. Abhishek Verma, Luis Pedrosa, Madhukar Korupolu, David Oppenheimer, Eric
   Tune, John Wilkes. "Large-scale cluster management at Google with Borg."
   EuroSys 2015.
   https://research.google/pubs/large-scale-cluster-management-at-google-with-borg/
8. Dirk Merkel. "Docker: Lightweight Linux Containers for Consistent
   Development and Deployment." Linux Journal, 2014.
   https://www.linuxjournal.com/content/docker-lightweight-linux-containers-consistent-development-and-deployment
9. Airbnb Engineering. "Airflow: a workflow management platform." 2015.
   https://nerds.airbnb.com/airflow/

## Provenance, Causality, And Receipts

10. Leslie Lamport. "Time, Clocks, and the Ordering of Events in a Distributed
    System." Communications of the ACM, 21(7), 1978.
    https://dl.acm.org/doi/10.1145/359545.359563
11. Luc Moreau, Paolo Missier, et al. "PROV-DM: The PROV Data Model." W3C
    Recommendation, 2013.
    https://www.w3.org/TR/prov-dm/

## Agent Tool Protocol Context

12. Model Context Protocol. Used as a protocol comparison point for tool and
    resource exposure; EasyRemote delegates MCP projection to the EasyNet
    daemon instead of implementing a separate MCP gateway in this facade.
    https://modelcontextprotocol.io/
