# Technical Translation Playbook

This playbook defines DBabel's core translation techniques for database and
technical-localization work. It complements `07_TRANSLATION_AND_MT_POLICY.md`;
it does not replace terminology evidence, project glossaries, format-specific
rules, deterministic QA, or human review.

The machine-readable registry is
[`../config/translation_techniques.yaml`](../config/translation_techniques.yaml).
Its schema is
[`../schemas/translation_techniques.schema.json`](../schemas/translation_techniques.schema.json).

## Boundary

The techniques are execution guidance, not source evidence.

- Worked examples are synthetic and are never evidence for a real vendor,
  product, version, UI, or deployment.
- Fluency never overrides source truth, scoped project rules, exact UI evidence,
  or protected technical content.
- A deterministic QA result remains a `POTENTIAL_ISSUE`.
- An AI suggestion is not human approval.
- Missing context remains missing. Do not silently repair an ambiguous source.

## Execution order

Use the techniques in this order when applicable:

1. identify document structure, translatable spans, and protected material;
2. determine technical concept, product/version scope, and text role;
3. resolve approved terminology, exact UI labels, and abbreviation policy;
4. preserve propositions, modality, conditions, scope, actors, objects, and sequence;
5. perform only supported translation transformations;
6. improve target-language technical naturalness;
7. run deterministic and semantic QA;
8. route unresolved or source-defect cases to `REVIEW`.

A lower-priority stylistic technique must never undo a higher-priority
protection, terminology, semantic, or scope constraint.

## Core techniques

| Technique | Category | Risk | Core rule |
|---|---|---:|---|
| `TECHNICAL_TOKEN_SHIELDING` | PROTECTION | HIGH | Identify non-translatable and executable spans before translating natural language. |
| `TERM_BEFORE_SENTENCE` | TERMINOLOGY | HIGH | Resolve material terminology constraints before polishing the surrounding sentence. |
| `CONCEPT_BEFORE_SURFACE_FORM` | TERMINOLOGY | HIGH | Determine which technical concept a word denotes before choosing its target-language surface form. |
| `PRODUCT_VERSION_SCOPING` | SCOPE | HIGH | Bind terminology and technical naming to the actual vendor, product, version, and text role. |
| `TEXT_ROLE_TRANSLATION` | TEXT_ROLE | MEDIUM | Translate according to whether text functions as prose, a label, heading, state, warning, table item, or code-adjacent content. |
| `UI_LABEL_ANCHORING` | TEXT_ROLE | HIGH | Use the exact verified UI label when documentation refers to a concrete product interface control. |
| `MODAL_STRENGTH_PRESERVATION` | SEMANTIC_FIDELITY | HIGH | Preserve obligation, prohibition, permission, recommendation, and prerequisite strength. |
| `LONG_SENTENCE_DECOMPOSITION` | STRUCTURE | MEDIUM | Split dense technical sentences only after mapping all propositions, actors, objects, conditions, and sequence relations. |
| `CONTROLLED_EXPLICITATION` | SEMANTIC_FIDELITY | HIGH | Add an omitted subject, object, or relation only when the surrounding context uniquely determines it. |
| `NO_INVENTED_CAUSALITY` | SEMANTIC_FIDELITY | HIGH | Do not introduce causal, purpose, result, or dependency relations that the source does not establish. |
| `TERMINOLOGY_VARIANT_GOVERNANCE` | TERMINOLOGY | MEDIUM | Manage preferred, admitted, forbidden, and protected variants instead of forcing one literal form everywhere. |
| `ABBREVIATION_LIFECYCLE` | TERMINOLOGY | MEDIUM | Control abbreviation introduction, expansion, reuse, casing, and scope across a document. |
| `SOURCE_DEFECT_ESCALATION` | REVIEW_GOVERNANCE | HIGH | Surface contradictions, ambiguity, and probable source defects instead of silently repairing them during translation. |
| `UI_DOCS_CONSISTENCY` | SCOPE | HIGH | Coordinate documentation wording with verified UI terminology while keeping prose and UI-label roles distinct. |
| `TARGET_LANGUAGE_TECHNICAL_NATURALNESS` | STYLE | LOW | Improve target-language technical prose only after terminology, propositional meaning, and protected content are stable. |

## Technique details

### 1. `TECHNICAL_TOKEN_SHIELDING`

Identify non-translatable and executable spans before translating natural language.

**Trigger patterns:** `identifier`, `parameter`, `command`, `path`, `filename`, `placeholder`, `url`, `environment_variable`, `version_literal`

**Required actions**

- Mark protected spans before generation.
- Preserve protected bytes unless a separate change is explicitly authorized.
- Run applicable deterministic integrity checks after translation.

**Do not**

- Translate or stylistically normalize executable identifiers.
- Rewrite paths, filenames, placeholders, or parameter names for fluency.

**Synthetic database-domain example**

- Source: 将参数 MAX_SESSIONS=200 写入 /opt/example/conf/example.ini，然后重启 ExampleDB。
- Unsafe: Write the parameter max_sessions=200 to /opt/example/conf/example_en.ini, and then restart ExampleDB.
- Preferred handling: Write MAX_SESSIONS=200 to /opt/example/conf/example.ini, and then restart ExampleDB.
- Why: The parameter token and path are executable or structural content, not prose.

**QA mapping:** deterministic = PLACEHOLDER_INTEGRITY, URL_INTEGRITY, PATH_INTEGRITY, FILENAME_INTEGRITY, CLI_OPTION_INTEGRITY, ENV_VAR_INTEGRITY, PROTECTED_LITERAL, VERSION_INTEGRITY; semantic = ACCURACY, DESIGN_AND_MARKUP.

**Unresolved context:** `PROTECT`.

### 2. `TERM_BEFORE_SENTENCE`

Resolve material terminology constraints before polishing the surrounding sentence.

**Trigger patterns:** `project_glossary_match`, `domain_term`, `vendor_term`, `repeated_concept`

**Required actions**

- Resolve scoped approved terminology before sentence-level stylistic refinement.
- Distinguish preferred, admitted, forbidden, and protected terms.
- Recheck the final sentence after grammatical inflection or restructuring.

**Do not**

- Generate a fluent sentence first and blindly replace terminology afterward.
- Treat frequency alone as terminology authority.

**Synthetic database-domain example**

- Source: 将主库切换为只读模式。
- Unsafe: Switch the master server to read-only mode.
- Preferred handling: Switch the primary database to read-only mode.
- Why: The example assumes a scoped project glossary has approved primary database for 主库.

**QA mapping:** deterministic = PREFERRED_TERM, FORBIDDEN_TERM; semantic = TERMINOLOGY, ACCURACY.

**Unresolved context:** `REVIEW`.

### 3. `CONCEPT_BEFORE_SURFACE_FORM`

Determine which technical concept a word denotes before choosing its target-language surface form.

**Trigger patterns:** `polysemy`, `ambiguous_database_term`, `same_form_multiple_concepts`

**Required actions**

- Identify the concept, object type, operation, and nearby technical context.
- Preserve ambiguity when the source does not resolve it.
- Escalate high-risk unresolved concepts to REVIEW.

**Do not**

- Translate an ambiguous database term from a bilingual dictionary alone.
- Choose the statistically common meaning without contextual evidence.

**Synthetic database-domain example**

- Source: 检查归档是否完整。
- Unsafe: Check whether archiving is complete.
- Preferred handling: REVIEW: determine whether 归档 denotes an archive file or set, an archive log, or the archiving process before translating.
- Why: The isolated surface form does not identify the technical object or operation.

**QA mapping:** deterministic = none; semantic = TERMINOLOGY, ACCURACY.

**Unresolved context:** `REVIEW`.

### 4. `PRODUCT_VERSION_SCOPING`

Bind terminology and technical naming to the actual vendor, product, version, and text role.

**Trigger patterns:** `vendor_specific_term`, `version_sensitive_term`, `renamed_parameter`, `cross_product_mapping`

**Required actions**

- Record applicable vendor, product, and version where material.
- Use same-product and same-version evidence for official naming when required.
- Keep older valid names in historical version scope.

**Do not**

- Propagate a terminology decision across database products by analogy.
- Back-port a renamed parameter or feature name to an older version without evidence.

**Synthetic database-domain example**

- Source: 版本 2.0 将旧参数名替换为新参数名。
- Unsafe: Use the new parameter name in every version of the product.
- Preferred handling: Use the parameter name documented for the actual product version; do not apply the rename to another version without evidence.
- Why: A valid rename in one version does not establish terminology for adjacent versions.

**QA mapping:** deterministic = VERSION_INTEGRITY; semantic = TERMINOLOGY, ACCURACY.

**Unresolved context:** `REVIEW`.

### 5. `TEXT_ROLE_TRANSLATION`

Translate according to whether text functions as prose, a label, heading, state, warning, table item, or code-adjacent content.

**Trigger patterns:** `same_token_different_role`, `ui_text`, `heading`, `state_text`

**Required actions**

- Identify the text role before selecting wording.
- Keep role-specific grammar, capitalization, and concision.
- Do not propagate a UI-label translation into prose merely because the source token matches.

**Do not**

- Apply one string replacement to every occurrence regardless of role.

**Synthetic database-domain example**

- Source: “打开”同时出现在按钮文本和“文件已打开”状态说明中。
- Unsafe: Translate every occurrence as Open.
- Preferred handling: Translate the button as an action label; translate the status occurrence according to its grammatical and semantic role.
- Why: Identical source forms can represent different text roles and therefore different target forms.

**QA mapping:** deterministic = none; semantic = TERMINOLOGY, STYLE, LINGUISTIC_CONVENTIONS.

**Unresolved context:** `REVIEW`.

### 6. `UI_LABEL_ANCHORING`

Use the exact verified UI label when documentation refers to a concrete product interface control.

**Trigger patterns:** `exact_ui_label`, `menu_item`, `button_name`, `dialog_label`

**Required actions**

- Verify the label against the applicable product and version when exact UI wording matters.
- Lock the verified label inside surrounding prose.
- Keep prose grammar separate from the exact label.

**Do not**

- Improve or paraphrase a verified UI label for style.
- Reuse a label from another version without confirmation.

**Synthetic database-domain example**

- Source: 单击“Start Service”，等待状态变为 Running。
- Unsafe: Click “Start the Service”, and wait until the status becomes Running.
- Preferred handling: Click “Start Service”, and wait until the status becomes Running.
- Why: Start Service is treated as an exact verified UI label in this example.

**QA mapping:** deterministic = PROTECTED_LITERAL; semantic = TERMINOLOGY, ACCURACY, DESIGN_AND_MARKUP.

**Unresolved context:** `REVIEW`.

### 7. `MODAL_STRENGTH_PRESERVATION`

Preserve obligation, prohibition, permission, recommendation, and prerequisite strength.

**Trigger patterns:** `must`, `must_not`, `should`, `may`, `only_after`, `required`, `recommended`

**Required actions**

- Identify modal force before restructuring the sentence.
- Preserve prerequisite and prohibition direction.
- Distinguish necessary conditions from sufficient conditions.

**Do not**

- Weaken must into should or recommendation.
- Turn only-after prerequisites into ordinary chronological suggestions.

**Synthetic database-domain example**

- Source: 只有校验通过后，才可以删除临时副本。
- Unsafe: Delete the temporary copy, and then validate it.
- Preferred handling: Delete the temporary copy only after validation passes.
- Why: The source establishes a prerequisite, not merely an event sequence.

**QA mapping:** deterministic = none; semantic = ACCURACY.

**Unresolved context:** `REVIEW`.

### 8. `LONG_SENTENCE_DECOMPOSITION`

Split dense technical sentences only after mapping all propositions, actors, objects, conditions, and sequence relations.

**Trigger patterns:** `multiple_actions`, `multiple_conditions`, `dense_clause_chain`, `ambiguous_attachment`

**Required actions**

- Map propositions before splitting.
- Preserve actor, action, object, condition, sequence, and scope.
- Recheck cross-sentence references after decomposition.

**Do not**

- Drop subordinate conditions to make the target shorter.
- Reorder operational steps solely for stylistic fluency.

**Synthetic database-domain example**

- Source: 备份完成并通过完整性校验后，停止目标服务，复制控制文件，然后在目标节点启动实例并确认状态正常。
- Unsafe: Stop the target service and start the instance after the backup, then validate and copy the control file.
- Preferred handling: After the backup completes and passes integrity validation, stop the target service and copy the control file. Then start the instance on the target node and verify its status.
- Why: The target may split the sentence, but the prerequisite and action order must remain intact.

**QA mapping:** deterministic = none; semantic = ACCURACY, LINGUISTIC_CONVENTIONS, STYLE.

**Unresolved context:** `REVIEW`.

### 9. `CONTROLLED_EXPLICITATION`

Add an omitted subject, object, or relation only when the surrounding context uniquely determines it.

**Trigger patterns:** `omitted_subject`, `omitted_object`, `pronoun_resolution`, `context_recovery`

**Required actions**

- Resolve the omitted element from explicit nearby context.
- Record REVIEW when more than one antecedent remains plausible.
- Prefer the narrowest supported explicit wording.

**Do not**

- Invent a technical object because it is common in similar deployments.
- Use world knowledge to silently repair an ambiguous source sentence.

**Synthetic database-domain example**

- Source: 上一句已明确对象为监听服务：“配置完成后启动。”
- Unsafe: After configuration is complete, start the database service.
- Preferred handling: After configuration is complete, start the listener service.
- Why: The explicit subject is permitted only because the preceding context uniquely identifies the listener service.

**QA mapping:** deterministic = none; semantic = ACCURACY.

**Unresolved context:** `REVIEW`.

### 10. `NO_INVENTED_CAUSALITY`

Do not introduce causal, purpose, result, or dependency relations that the source does not establish.

**Trigger patterns:** `adjacent_sentences`, `therefore`, `because`, `so_that`, `result_relation`

**Required actions**

- Separate chronology from causality.
- Add causal connectors only when supported by the source or scoped evidence.

**Do not**

- Use because, therefore, so that, or equivalent connectors merely to make prose smoother.

**Synthetic database-domain example**

- Source: 主库写入日志。备库接收日志。
- Unsafe: The primary database writes logs so that the standby database can receive them.
- Preferred handling: The primary database writes logs. The standby database receives logs.
- Why: The two source propositions are adjacent, but the source does not explicitly encode a purpose relation.

**QA mapping:** deterministic = none; semantic = ACCURACY.

**Unresolved context:** `REVIEW`.

### 11. `TERMINOLOGY_VARIANT_GOVERNANCE`

Manage preferred, admitted, forbidden, and protected variants instead of forcing one literal form everywhere.

**Trigger patterns:** `preferred_term`, `admitted_variant`, `forbidden_variant`, `grammatical_variant`

**Required actions**

- Apply project-approved term behavior within its declared scope.
- Allow admitted variants only where their text role and grammar permit.
- Keep forbidden forms detectable after generation.

**Do not**

- Treat every non-preferred variant as an error when the glossary explicitly admits it.
- Use an admitted shorthand outside its approved role or scope.

**Synthetic database-domain example**

- Source: 项目术语表：preferred=primary database；admitted=primary；forbidden=master database。
- Unsafe: Switch the master database to read-only mode.
- Preferred handling: Use primary database in normal prose, or the admitted primary form only where the scoped project rule permits it.
- Why: Terminology governance distinguishes preferred usage from valid scoped variants and forbidden forms.

**QA mapping:** deterministic = PREFERRED_TERM, FORBIDDEN_TERM; semantic = TERMINOLOGY, STYLE.

**Unresolved context:** `REVIEW`.

### 12. `ABBREVIATION_LIFECYCLE`

Control abbreviation introduction, expansion, reuse, casing, and scope across a document.

**Trigger patterns:** `acronym`, `first_use`, `full_form`, `abbreviation_reuse`

**Required actions**

- Determine whether a recognized abbreviation already exists in the scoped material.
- Apply first-use and subsequent-use rules consistently.
- Preserve casing and avoid creating undocumented abbreviations.

**Do not**

- Invent an abbreviation to shorten the target text.
- Expand a product-specific abbreviation using an unverified full form.

**Synthetic database-domain example**

- Source: 首次出现：“灾难恢复（DR）”；后文：“DR 演练”。
- Unsafe: Use DR at first occurrence without an established expansion, or repeat the full form at every occurrence.
- Preferred handling: Use disaster recovery (DR) at first occurrence and DR drill in later scoped occurrences.
- Why: The example demonstrates lifecycle handling rather than asserting a product-specific abbreviation.

**QA mapping:** deterministic = none; semantic = TERMINOLOGY, STYLE.

**Unresolved context:** `REVIEW`.

### 13. `SOURCE_DEFECT_ESCALATION`

Surface contradictions, ambiguity, and probable source defects instead of silently repairing them during translation.

**Trigger patterns:** `source_conflict`, `scope_conflict`, `probable_copy_error`, `contradictory_instruction`

**Required actions**

- Identify the conflicting source spans.
- State what evidence or author confirmation would resolve the conflict.
- Keep the translation decision at REVIEW until the source issue is resolved when material.

**Do not**

- Choose the operationally familiar interpretation and present it as source truth.
- Hide a source defect by producing a clean target sentence.

**Synthetic database-domain example**

- Source: 标题：“仅在主机 A 执行”；步骤：“在主机 A 和 B 上执行以下命令”。
- Unsafe: Resolve the conflict by translating the step as host A only because that seems more typical.
- Preferred handling: REVIEW: the source execution scope conflicts; request authoritative clarification before normalizing the target.
- Why: Translation must not silently become source-authoring when the source contains a material contradiction.

**QA mapping:** deterministic = none; semantic = ACCURACY.

**Unresolved context:** `REVIEW`.

### 14. `UI_DOCS_CONSISTENCY`

Coordinate documentation wording with verified UI terminology while keeping prose and UI-label roles distinct.

**Trigger patterns:** `documentation_ui_reference`, `ui_label_mismatch`, `same_feature_multiple_surfaces`

**Required actions**

- Verify exact labels against the applicable UI when required.
- Use the exact label as a locked reference inside natural prose.
- Keep conceptual prose terminology distinct from exact UI strings when appropriate.

**Do not**

- Force all prose wording to equal the UI label.
- Paraphrase an exact UI label while presenting it as the interface text.

**Synthetic database-domain example**

- Source: 正文：“单击启动服务按钮”；同版本界面按钮实际标签为 “Start Service”。
- Unsafe: Click the Start button on the Service Management page.
- Preferred handling: Click Start Service on the Service Management page.
- Why: The prose remains natural while the verified UI label is preserved exactly.

**QA mapping:** deterministic = PROTECTED_LITERAL; semantic = TERMINOLOGY, ACCURACY, STYLE.

**Unresolved context:** `REVIEW`.

### 15. `TARGET_LANGUAGE_TECHNICAL_NATURALNESS`

Improve target-language technical prose only after terminology, propositional meaning, and protected content are stable.

**Trigger patterns:** `literal_translation`, `nominalization`, `awkward_technical_english`, `redundant_operation_noun`

**Required actions**

- Apply natural target-language syntax after hard constraints are satisfied.
- Prefer direct technical verbs where meaning is unchanged.
- Re-run terminology and semantic checks after stylistic refinement.

**Do not**

- Trade technical precision for elegance.
- Delete repeated technical terms merely to avoid stylistic repetition.

**Synthetic database-domain example**

- Source: 进行数据库参数的配置。
- Unsafe: Carry out the configuration operation of database parameters.
- Preferred handling: Configure the database parameters.
- Why: Naturalness is a final constrained refinement, not permission to alter technical meaning.

**QA mapping:** deterministic = none; semantic = LINGUISTIC_CONVENTIONS, STYLE.

**Unresolved context:** `REVIEW`.

## Controlled transformation model

Translation is not treated as an unconstrained rewrite. DBabel records a small
set of transformation types so that higher-risk changes can be distinguished
from ordinary grammatical realization.

| Transformation | Risk | Meaning |
|---|---:|---|
| `TERM_SUBSTITUTION` | MEDIUM | Replace a term with a scoped approved or evidenced equivalent. |
| `CLAUSE_REORDERING` | MEDIUM | Reorder clauses while preserving conditions, scope, and logical relations. |
| `SENTENCE_SPLIT` | MEDIUM | Split one source sentence into multiple target sentences without losing propositions. |
| `SENTENCE_MERGE` | HIGH | Merge source sentences only when proposition boundaries and logical relations remain explicit. |
| `EXPLICITATION` | HIGH | Make an implicit element explicit only when the context uniquely supports it. |
| `IMPLICITATION` | HIGH | Omit an explicit source element only when meaning and constraints remain fully recoverable. |
| `VOICE_CHANGE` | LOW | Change grammatical voice without changing actor, action, object, or responsibility. |
| `NOMINALIZATION_SHIFT` | LOW | Convert nominalized technical wording to a direct verb construction or vice versa. |
| `UI_LABEL_LOCK` | LOW | Preserve an exact verified UI label instead of stylistically rewriting it. |
| `DNT_PRESERVATION` | LOW | Preserve do-not-translate or executable material exactly. |
| `ABBREVIATION_EXPANSION` | MEDIUM | Introduce or expand an abbreviation only under an established abbreviation policy. |
| `PUNCTUATION_LOCALIZATION` | LOW | Adapt punctuation to target-language conventions without changing executable or UI syntax. |

A transformation being listed as `allowed` does not mean it is automatically
correct. It means the technique does not prohibit that transformation when its
preconditions are satisfied. `restricted` transformations require the agent to
avoid the operation unless stronger task-specific evidence or explicit user
authorization resolves the risk.

## QA and Workbench integration

Technique violations should remain distinguishable from deterministic QA.

Examples:

- placeholder loss can be detected deterministically;
- modal weakening normally requires semantic review;
- an unverified UI-label rewrite requires product/version evidence;
- awkward but semantically correct English is a style issue, not automatically
  an accuracy failure;
- a source contradiction is a source-review condition, not permission to invent
  a clean target sentence.

When a proposed bilingual change requires approval, route it through Review
Workbench. The Workbench decision remains separate from the technique that
motivated the suggestion.

## Maintenance rules

When adding a technique:

1. give it a stable uppercase ID;
2. state the risk and trigger conditions;
3. define what must and must not change;
4. map only real deterministic checks that DBabel implements;
5. include semantic QA dimensions where human judgment is required;
6. provide a synthetic example that does not masquerade as vendor evidence;
7. update the schema or transformation vocabulary only when the new rule cannot
   be represented safely by the existing contract;
8. keep the registry, router, tests, and this playbook synchronized.

Do not add stylistic preferences merely because they sound better in English.
A rule belongs here only when it repeatedly improves technical translation
accuracy, consistency, reviewability, or structural safety.

## Design inspirations

The following public projects and guidance informed the shape of this playbook.
They support general localization patterns, not DBabel findings for a specific
vendor task.

- Weblate, “Translating special text safely”:
  https://docs.weblate.org/en/latest/user/translating.html
- Mozilla Fluent, Terms:
  https://projectfluent.org/fluent/guide/terms.html
- Mozilla Fluent, Variables and Selectors:
  https://projectfluent.org/fluent/guide/variables.html
  and https://projectfluent.org/fluent/guide/selectors.html
- MQM Core Typology:
  https://www.themqm.org/mqm-pillars/the-mqm-core-typology/
- Google developer documentation style guide, global audience:
  https://developers.google.com/style/translation
- Microsoft language resources:
  https://learn.microsoft.com/en-us/globalization/reference/microsoft-language-resources
- Translate Toolkit `pofilter` checks:
  https://docs.translatehouse.org/projects/translate-toolkit/en/latest/commands/pofilter_tests.html
- Okapi Framework filter and inline-code concepts:
  https://okapiframework.org/devguide/filters.html

DBabel adapts these ideas to evidence-driven database terminology review,
structured technical documents, protected technical literals, and explicit
human approval.
