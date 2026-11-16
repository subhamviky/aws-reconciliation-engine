# Design documents

| Document | Word | Covers |
|---|---|---|
| [Reconciliation Engine — Design](RECONCILIATION_DESIGN.md) | [docx](Reconciliation_Design_Document.docx) | `reconciliation-service`: HLD (context, framework fit, AWS deployment, integration, identity, model access) and LLD (data, classes, contracts, sequences, states, failure model, configuration, verification, gaps) |

The document follows the structure of the E2A design documents (`e2a-framework/docs/design/`), the A2C, G2C and P0 designs (`a2c-framework/docs/design/`) and the managed-provider designs (`e2a-managed-providers/docs/design/`), and refers to them rather than repeating them.

Diagrams are in `diagrams/` (Graphviz `.dot`, PlantUML `.puml` with `common/style.puml`) and rendered to `images/`:

```
dot -Tpng -Gdpi=220 diagrams/<name>.dot -o images/<name>.png
java -jar plantuml.jar -tpng -o ../images diagrams/<name>.puml
```
