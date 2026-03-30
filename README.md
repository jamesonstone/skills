# 🤖 Agent Skills

```plaintext
╔════════════════════════════════════════════════════════╗
║                                                        ║
║           ✨ AGENT SKILLS VAULT v∞ ✨                  ║
║                                                        ║
║      curated • serviced • actively evolving            ║
║                                                        ║
╚════════════════════════════════════════════════════════╝
```

> A living, breathing repository of fine-tuned agent capabilities. Currently under **active development** with new skills being forged, refined, and deployed on an ongoing basis. 🚀

## What Lives Here

This is a personal collection of **agent skills**—specialized toolkits and frameworks that power intelligent agents. Each skill is:

- **Curated** with intention and care
- **Serviced** regularly as needs evolve
- **Battle-tested** across real-world agent implementations
- **Constantly improving** (never truly finished)

## ⚙️ Current Status

🔧 **Always Building** — This repo is in perpetual active development. Expect:

- New skills arriving regularly
- Existing skills getting sharper
- Experimental ideas being tested
- Documentation evolving alongside the code

Think of it as a living laboratory for multi-agent architectures.

## Skill Archive Automation

Every top-level non-hidden directory in this repository is treated as a skill.
Each skill must contain a committed zip archive at:

- `<skill>/<skill>.zip`

The archive is rebuilt deterministically from the full skill directory, while
excluding only the generated zip itself.

### Local pre-commit setup

Activate the repo-managed hook once per clone:

```bash
git config core.hooksPath .githooks
```

After that, every commit automatically regenerates and stages zip files for any
skills touched in the index.

### Manual commands

```bash
python3 .skill-tools/package_skills.py --mode sync
python3 .skill-tools/package_skills.py --mode verify
```

`sync` refreshes committed zip files in the working tree.
`verify` fails if any committed zip file is missing or stale.

### CI

GitHub Actions runs the same verifier on every push and pull request and fails
when a committed skill archive is out of date.

## 👥 Maintainers

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/jamesonstone">
        <img src="https://github.com/jamesonstone.png" width="100px;" alt="Jameson Stone"/>
        <br />
        <sub><b>Jameson Stone</b></sub>
      </a>
      <br />
      <sub>Lead Maintainer</sub>
    </td>
  </tr>
</table>
