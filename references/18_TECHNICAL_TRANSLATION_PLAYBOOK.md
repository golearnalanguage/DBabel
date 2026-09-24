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

## Candidate routing boundary

The machine-readable `triggers` in this playbook may route explicit unit-level observations to candidate techniques. Matching is exact rather than fuzzy; task mode and concrete text role constrain applicability; unknown or unmatched signals remain visible; and a candidate does not establish that a translation failure occurred. Semantic adjudication is required before `finding.technique` is populated. A candidate never chooses a semantic decision or authorizes repair.

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
| `CONCEPT_BEFORE_SURFACE_FORM` | TERMINOLOGY | HIGH | Determine which technical concept a word denotes before choosing its target-language surface form. |
| `PRODUCT_VERSION_SCOPING` | SCOPE | HIGH | Bind terminology and technical naming to the actual vendor, product, version, and text role. |
| `TEXT_ROLE_TRANSLATION` | TEXT_ROLE | MEDIUM | Translate according to whether text functions as prose, a label, heading, state, warning, table item, or code-adjacent content. |
| `UI_LABEL_ANCHORING` | TEXT_ROLE | HIGH | Use the exact verified UI label when documentation refers to a concrete product interface control. |
| `MODAL_STRENGTH_PRESERVATION` | SEMANTIC_FIDELITY | HIGH | Preserve obligation, prohibition, permission, recommendation, and prerequisite strength. |
| `CONDITION_ACTION_RESULT_PRESERVATION` | SEMANTIC_FIDELITY | HIGH | Preserve which conditions govern which actions and results in technical instructions. |
| `SCOPE_PRESERVATION` | SEMANTIC_FIDELITY | HIGH | Preserve quantifiers, exclusions, selection boundaries, and other scope-limiting language. |
| `PROPOSITION_PRESERVING_REORDERING` | STRUCTURE | MEDIUM | Allow target-language reordering only when proposition roles and logical relationships remain unchanged. |
| `LONG_SENTENCE_DECOMPOSITION` | STRUCTURE | MEDIUM | Split dense technical sentences only after mapping all propositions, actors, objects, conditions, and sequence relations. |
| `CONTROLLED_EXPLICITATION` | SEMANTIC_FIDELITY | HIGH | Add an omitted subject, object, or relation only when the surrounding context uniquely determines it. |
| `NO_INVENTED_CAUSALITY` | SEMANTIC_FIDELITY | HIGH | Do not introduce causal, purpose, result, or dependency relations that the source does not establish. |
| `TERMINOLOGY_VARIANT_GOVERNANCE` | TERMINOLOGY | MEDIUM | Manage preferred, admitted, forbidden, and protected variants instead of forcing one literal form everywhere. |
| `ABBREVIATION_LIFECYCLE` | TERMINOLOGY | MEDIUM | Control abbreviation introduction, expansion, reuse, casing, and scope across a document. |
| `SOURCE_DEFECT_ESCALATION` | REVIEW_GOVERNANCE | HIGH | Surface contradictions, ambiguity, and probable source defects instead of silently repairing them during translation. |

## Workflow-level principles

Some important translation rules remain workflow-level constraints rather than
independent machine technique IDs.

- Resolve scoped terminology before sentence-level stylistic polishing. This
  ordering is already defined by `07_TRANSLATION_AND_MT_POLICY.md`.
- UI/documentation consistency is handled compositionally by
  `TEXT_ROLE_TRANSLATION` and `UI_LABEL_ANCHORING`, rather than by a duplicate
  standalone technique.
- Target-language technical naturalness remains the final constrained refinement
  stage. It must not override terminology, protected content, propositions,
  modality, conditions, scope, or technical roles.

This separation keeps the catalog focused on discrete technical-translation
failure modes rather than duplicating workflow sequencing or general style goals.

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

**Unresolved context:** `REVIEW`.

### 2. `CONCEPT_BEFORE_SURFACE_FORM`

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

### 3. `PRODUCT_VERSION_SCOPING`

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

### 4. `TEXT_ROLE_TRANSLATION`

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

### 5. `UI_LABEL_ANCHORING`

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

### 6. `MODAL_STRENGTH_PRESERVATION`

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

### 7. `CONDITION_ACTION_RESULT_PRESERVATION`

Preserve which conditions govern which actions and results in technical instructions.

**Trigger patterns:** `conditional_clause`, `precondition`, `postcondition`, `action_result`, `exception_condition`

**Required actions**

- Identify each condition, governed action, object, and stated result.
- Preserve which condition applies to which operation.
- Keep prerequisites and failure branches attached to the correct action.

**Do not**

- Turn a conditional instruction into an unconditional action.
- Detach a failure or exception condition from the operation it governs.

**Synthetic database-domain example**

- Source: 连接成功后执行备份；若校验失败，不得删除原备份集。
- Unsafe: Run the backup and delete the original backup set after validation.
- Preferred handling: After the connection succeeds, run the backup. If validation fails, do not delete the original backup set.
- Why: The success condition and failure prohibition govern different actions and must remain attached to them.

**QA mapping:** deterministic = none; semantic = ACCURACY.

**Unresolved context:** `REVIEW`.

### 8. `SCOPE_PRESERVATION`

Preserve quantifiers, exclusions, selection boundaries, and other scope-limiting language.

**Trigger patterns:** `all`, `any`, `each`, `both`, `only`, `current`, `selected`, `either`, `except`, `unless`

**Required actions**

- Identify the exact span governed by each quantifier or limiter.
- Preserve inclusions, exclusions, and selection boundaries.
- Keep modifiers attached to the technical object they constrain.

**Do not**

- Widen a selected or current subset into all objects.
- Narrow an all or each requirement without source support.
- Drop except, only, unless, or equivalent limiting meaning.

**Synthetic database-domain example**

- Source: 仅删除当前节点上已选中的日志文件，其他节点不处理。
- Unsafe: Delete the log files from all nodes.
- Preferred handling: Delete only the selected log files on the current node; do not process the other nodes.
- Why: Only, selected, current, and the exclusion of other nodes jointly define the operation scope.

**QA mapping:** deterministic = none; semantic = ACCURACY.

**Unresolved context:** `REVIEW`.

### 9. `PROPOSITION_PRESERVING_REORDERING`

Allow target-language reordering only when proposition roles and logical relationships remain unchanged.

**Trigger patterns:** `source_target_information_order`, `topic_comment_structure`, `role_sensitive_reordering`, `clause_reordering`

**Required actions**

- Map actor, action, object, state, and logical relation before reordering.
- Verify all source propositions remain present after reordering.
- Recheck technical roles after grammatical voice or clause-order changes.

**Do not**

- Swap actor and recipient roles while improving target-language order.
- Change operation sequence merely because another order reads more naturally.

**Synthetic database-domain example**

- Source: 归档日志由备库接收，主库负责发送。
- Unsafe: The standby database sends the archive logs to the primary database.
- Preferred handling: The primary database sends the archive logs, and the standby database receives them.
- Why: Clause order may change for English readability, but sender and receiver roles must not change.

**QA mapping:** deterministic = none; semantic = ACCURACY, LINGUISTIC_CONVENTIONS.

**Unresolved context:** `REVIEW`.

### 10. `LONG_SENTENCE_DECOMPOSITION`

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

### 11. `CONTROLLED_EXPLICITATION`

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

### 12. `NO_INVENTED_CAUSALITY`

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

### 13. `TERMINOLOGY_VARIANT_GOVERNANCE`

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

### 14. `ABBREVIATION_LIFECYCLE`

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

### 15. `SOURCE_DEFECT_ESCALATION`

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
