# dpm_os

An operating system for a data product manager. One markdown repo per product decision: seven context files, three manual gates, one weekly packet, one append-only decision log, and a validator that keeps every claim tagged with its source. Built for Claude Code. No database, no agents beyond one initializer, nothing that runs without a person.

## The habit loop

1. **Monday: the packet.** One page. Decisions requested first, then changed evidence, then blockers by owner.
2. **When a decision is due: the gate.** Intake, engineering commitment, or controlled launch. A checklist with named acceptance owners. It flags; a person decides.
3. **Friday: the log.** One row per decision, one record per decision, one row per risk. Run the maintenance checklist.

## Install

```bash
git clone https://github.com/hollandkevint/dpm_os.git
cp -R dpm_os/.claude/skills/dpm-os <your-project>/.claude/skills/dpm-os
cd <your-project> && claude
```

Then run `/dpm-os`. Full steps, the skill library it expects, and uninstall are in [docs/install.md](docs/install.md).

## What you get

```text
INDEX.md                 current decision + area table
CLAUDE.md                operating manual for any agent
context/                 strategy, product, consumers, decision rights, data contract, metrics, boundaries
rules/                   intake, commitment, launch gates
packets/                 weekly decision packet template
decisions/               schema, log, one record per decision
risks/                   risk log
source/  ingestion/      verbatim inputs and the notes that cite them
maintenance/             weekly checklist, capability scorecard, owner guide
scripts/validate.py      required files, links, decision fields, provenance tags
```

## Where it comes from

The gates, packet, and decision log encode the Data Product Operating System (DPOS): the handoff between roles is the unit that gets engineered. The analysis skills the initializer points at live in [data-product-operator](https://github.com/hollandkevint/data-product-operator), a separate install.

## Verify

```bash
python3 -m unittest discover tests
python3 .claude/skills/dpm-os/scaffold/scripts/validate.py .claude/skills/dpm-os/scaffold
```

## License

Apache-2.0. See [LICENSE](LICENSE).
