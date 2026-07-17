(function (root, factory) {
  var engine = factory();
  if (typeof module === 'object' && module.exports) module.exports = engine;
  if (root) root.CatalystGritEngine = engine;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var VERSION = '1.2.0';
  var METHOD_PATH = ['context', 'trigger', 'impact', 'pressure', 'constraints', 'supports', 'capacity', 'response', 'learning', 'next steps', 'human review'];
  var DEFAULT_ACTIONS = ['Name the smallest recoverable next step', 'Review support and constraints', 'Schedule a short follow-up review'];
  var DOMAINS = ['work', 'learning', 'health_wellbeing', 'relationship', 'project', 'career', 'community', 'organization', 'other'];
  var RECORD_STATUSES = ['draft', 'active', 'under_review', 'reviewed', 'archived'];
  var REVIEW_STATUSES = ['not_reviewed', 'needs_review', 'in_review', 'reviewed', 'changes_requested'];
  var TRIGGER_TYPES = ['setback', 'delay', 'conflict', 'constraint_change', 'capacity_change', 'external_event', 'other'];
  var IMPACT_SCOPES = ['task', 'workstream', 'project', 'team', 'organization', 'personal', 'multi_system', 'other'];
  var CONSTRAINT_TYPES = ['time', 'resource', 'dependency', 'information', 'coordination', 'policy', 'capacity', 'other'];
  var CONTROLLABILITY = ['controllable', 'influence', 'limited', 'unknown'];
  var SUPPORT_TYPES = ['person', 'team', 'tool', 'process', 'time', 'funding', 'information', 'other'];
  var ACTION_STATUSES = ['planned', 'in_progress', 'completed', 'paused'];
  var PROVENANCE_SOURCES = ['direct_entry', 'browser', 'cli', 'api', 'import', 'migration'];
  var INTERPRETATION_LIMITS = [
    "Describes recorded recovery conditions, not a person's character.",
    'Does not diagnose mental health, predict outcomes, or replace professional support.',
    'Must not be used for employee ranking, automated eligibility, or performance evaluation.',
    'Generated findings require human review when used for consequential decisions.'
  ];
  var DEFAULT_PROFILE = {
    profile_id: 'cg-recovery-conditions',
    profile_version: '1.2.0',
    calculation_spec: 'weighted-components-v1',
    component_weights: {
      impact_buffer: 15, pressure_buffer: 15, energy_capacity: 15, support_capacity: 15,
      clarity_capacity: 15, action_readiness: 15, constraint_manageability: 10
    },
    thresholds: { stable: 75, focused_support: 55, fragile: 35 }
  };

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function round(value, places) { var factor = Math.pow(10, places); return Math.round(value * factor) / factor; }
  function issue(path, code, message, value) {
    var item = { path: path, code: code, message: message };
    if (value !== undefined && value !== null) item.value = value;
    return item;
  }
  function ValidationError(issues) {
    this.name = 'GritValidationError';
    this.issues = Array.isArray(issues) ? issues : [issues];
    this.message = this.issues.map(function (item) { return item.path + ': ' + item.message; }).join('; ');
    if (Error.captureStackTrace) Error.captureStackTrace(this, ValidationError);
  }
  ValidationError.prototype = Object.create(Error.prototype);
  ValidationError.prototype.constructor = ValidationError;
  ValidationError.prototype.toJSON = function () {
    return { error: 'validation_failed', message: 'The recovery-record request is invalid.', issues: clone(this.issues) };
  };
  function fail(path, code, message, value) { throw new ValidationError(issue(path, code, message, value)); }
  function isObject(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
  function mapping(value, path) { if (!isObject(value)) fail(path, 'type_error', 'Must be an object.', value); return value; }
  function rejectUnknown(value, allowed, path) {
    var unknown = Object.keys(value).filter(function (key) { return allowed.indexOf(key) === -1; }).sort();
    if (unknown.length) fail(path, 'unknown_field', 'Unsupported field(s): ' + unknown.join(', ') + '. Use the extensions object for namespaced additions.', unknown);
  }
  function text(value, path, defaultValue, required) {
    var result = value === undefined || value === null ? (defaultValue || '') : String(value).trim();
    if (required && !result) fail(path, 'required', 'Must not be empty.');
    return result;
  }
  function optionalText(value) { if (value === undefined || value === null) return null; var result = String(value).trim(); return result || null; }
  function clampScale(value, path) {
    var number = Number(value === undefined || value === null ? 5 : value);
    if (Number.isNaN(number)) fail(path, 'numeric_required', 'Must be numeric.', value);
    return Math.max(1, Math.min(10, number));
  }
  function integer(value, path, defaultValue) {
    var number = Math.trunc(Number(value === undefined || value === null ? defaultValue : value));
    if (Number.isNaN(number)) fail(path, 'integer_required', 'Must be numeric.', value);
    return Math.max(1, number);
  }
  function nullableNumber(value, path) {
    if (value === undefined || value === null || value === '') return null;
    var number = Number(value);
    if (Number.isNaN(number)) fail(path, 'numeric_required', 'Must be numeric or null.', value);
    if (number < 0) fail(path, 'minimum', 'Must be at least 0.', value);
    return number;
  }
  function enumValue(value, path, allowed, defaultValue) {
    var result = text(value, path, defaultValue, false) || defaultValue;
    if (allowed.indexOf(result) === -1) fail(path, 'enum', 'Must be one of: ' + allowed.slice().sort().join(', ') + '.', value);
    return result;
  }
  function stringList(value, path) {
    if (value === undefined || value === null || value === '') return [];
    var source = Array.isArray(value) ? value : (typeof value === 'string' ? value.split('\n') : null);
    if (!source) fail(path, 'type_error', 'Must be an array of strings or newline-delimited text.', value);
    return source.map(function (item) { return String(item).trim(); }).filter(Boolean);
  }
  function normalizeTimestamp(value, path, defaultValue) {
    var source = text(value, path, defaultValue, false) || defaultValue;
    var date = new Date(source);
    if (Number.isNaN(date.getTime()) || !/(Z|[+-]\d\d:\d\d)$/.test(source)) fail(path, 'date_time', 'Must be an ISO 8601 date-time with a timezone.', value);
    return date.toISOString().replace('.000Z', 'Z');
  }
  function optionalTimestamp(value, path) { return value === undefined || value === null || value === '' ? null : normalizeTimestamp(value, path, ''); }
  function optionalDate(value, path) {
    if (value === undefined || value === null || value === '') return null;
    var source = String(value).trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(source) || Number.isNaN(new Date(source + 'T00:00:00Z').getTime())) fail(path, 'date', 'Must use YYYY-MM-DD.', value);
    return source;
  }
  function nowISO() { return new Date().toISOString().replace('.000Z', 'Z'); }
  function randomRecordId() {
    var id;
    if (typeof crypto !== 'undefined' && crypto.randomUUID) id = crypto.randomUUID().replace(/-/g, '');
    else id = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'.replace(/x/g, function () { return Math.floor(Math.random() * 16).toString(16); });
    return 'cgr_' + id;
  }
  function normalizeExtensions(value) {
    if (value === undefined || value === null || value === '') return {};
    var output = mapping(value, '$.extensions');
    var invalid = Object.keys(output).filter(function (key) { return !/^[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)+$/.test(key); });
    if (invalid.length) fail('$.extensions', 'extension_namespace', 'Extension keys must be namespaced, for example org.example.field.', invalid);
    return clone(output);
  }
  function normalizeActions(value, path, defaultActions) {
    var source;
    if (value === undefined || value === null || value === '') source = [];
    else if (Array.isArray(value)) source = value;
    else if (typeof value === 'string') source = value.split('\n');
    else fail(path, 'type_error', 'Must be an array or newline-delimited text.', value);
    var actions = [];
    source.forEach(function (item, index) {
      var itemPath = path + '[' + index + ']';
      if (isObject(item)) {
        rejectUnknown(item, ['title', 'status', 'owner', 'target_date'], itemPath);
        actions.push({
          title: text(item.title, itemPath + '.title', '', true),
          status: enumValue(item.status, itemPath + '.status', ACTION_STATUSES, 'planned'),
          owner: optionalText(item.owner),
          target_date: optionalDate(item.target_date, itemPath + '.target_date')
        });
      } else {
        var title = text(item, itemPath, '', false);
        if (title) actions.push({ title: title, status: 'planned', owner: null, target_date: null });
      }
    });
    if (!actions.length && defaultActions) actions = DEFAULT_ACTIONS.map(function (title) { return { title: title, status: 'planned', owner: null, target_date: null }; });
    return actions;
  }
  function normalizeConstraints(value, path) {
    if (value === undefined || value === null || value === '') return [];
    var source = Array.isArray(value) ? value : (typeof value === 'string' ? value.split('\n') : null);
    if (!source) fail(path, 'type_error', 'Must be an array or newline-delimited text.', value);
    var output = [];
    source.forEach(function (item, index) {
      var itemPath = path + '[' + index + ']';
      if (isObject(item)) {
        rejectUnknown(item, ['label', 'type', 'controllability'], itemPath);
        output.push({
          label: text(item.label, itemPath + '.label', '', true),
          type: enumValue(item.type, itemPath + '.type', CONSTRAINT_TYPES, 'other'),
          controllability: enumValue(item.controllability, itemPath + '.controllability', CONTROLLABILITY, 'unknown')
        });
      } else {
        var label = text(item, itemPath, '', false);
        if (label) output.push({ label: label, type: 'other', controllability: 'unknown' });
      }
    });
    return output;
  }
  function normalizeSupports(value, path) {
    if (value === undefined || value === null || value === '') return [];
    var source = Array.isArray(value) ? value : (typeof value === 'string' ? value.split('\n') : null);
    if (!source) fail(path, 'type_error', 'Must be an array or newline-delimited text.', value);
    var output = [];
    source.forEach(function (item, index) {
      var itemPath = path + '[' + index + ']';
      if (isObject(item)) {
        rejectUnknown(item, ['label', 'type', 'reliability'], itemPath);
        output.push({
          label: text(item.label, itemPath + '.label', '', true),
          type: enumValue(item.type, itemPath + '.type', SUPPORT_TYPES, 'other'),
          reliability: clampScale(item.reliability === undefined ? 5 : item.reliability, itemPath + '.reliability')
        });
      } else {
        var label = text(item, itemPath, '', false);
        if (label) output.push({ label: label, type: 'other', reliability: 5 });
      }
    });
    return output;
  }
  function migrateV1Request(data) {
    var review = String(data.review_status || 'draft');
    var recordStatus = { draft: 'draft', needs_review: 'under_review', reviewed: 'reviewed' }[review] || 'draft';
    var humanStatus = { draft: 'not_reviewed', needs_review: 'needs_review', reviewed: 'reviewed' }[review] || 'not_reviewed';
    var challenge = String(data.challenge || '').trim() || 'Unspecified challenge';
    return {
      metadata: { status: recordStatus, provenance: { created_by: 'self', source: 'migration', source_schema_version: '1.0.1', source_record_id: null, notes: 'Migrated from the v1.0.x flat recovery-record request.' } },
      input: {
        context: { title: challenge, domain: data.domain || 'project', description: '', stakeholders: [] },
        trigger: { summary: challenge, type: 'setback', occurred_at: null },
        impact: { severity: data.impact_severity === undefined ? 5 : data.impact_severity, scope: 'project', description: '' },
        pressure: { level: data.pressure_level === undefined ? 5 : data.pressure_level, sources: [] },
        constraints: { items: [] }, supports: { level: data.support_level === undefined ? 5 : data.support_level, available: [] },
        capacity: { energy_level: data.energy_level === undefined ? 5 : data.energy_level, clarity_level: data.clarity_level === undefined ? 5 : data.clarity_level, available_time_hours: null, time_horizon_days: data.time_horizon_days === undefined ? 14 : data.time_horizon_days },
        response: { actions: data.recovery_actions, current_strategy: '' }, learning: { observations: [], assumptions: [], adaptations: [] },
        next_steps: { actions: [], checkpoint_date: null, success_signal: '' }
      },
      human_review: { review_status: humanStatus, reviewer: null, reviewed_at: null, notes: '', accepted_findings: [], rejected_findings: [], override_state: null },
      extensions: {}
    };
  }
  function normalizeMetadata(value, sourceSchemaVersion) {
    var metadata = mapping(value || {}, '$.metadata');
    rejectUnknown(metadata, ['record_id', 'schema_version', 'engine_version', 'created_at', 'updated_at', 'status', 'provenance'], '$.metadata');
    var recordId = text(metadata.record_id, '$.metadata.record_id', randomRecordId(), false);
    if (!/^cgr_[0-9a-f]{32}$/.test(recordId)) fail('$.metadata.record_id', 'record_id', 'Must match cgr_ followed by 32 lowercase hexadecimal characters.', recordId);
    if (metadata.schema_version && [VERSION, '1.0.1'].indexOf(String(metadata.schema_version)) === -1) fail('$.metadata.schema_version', 'schema_version', 'Unsupported source schema version: ' + metadata.schema_version + '.', metadata.schema_version);
    if (metadata.engine_version && String(metadata.engine_version) !== VERSION) fail('$.metadata.engine_version', 'engine_version', 'Requests may not select a different engine version.', metadata.engine_version);
    var created = normalizeTimestamp(metadata.created_at, '$.metadata.created_at', nowISO());
    var updated = normalizeTimestamp(metadata.updated_at, '$.metadata.updated_at', created);
    if (updated < created) fail('$.metadata.updated_at', 'chronology', 'Must not be earlier than created_at.', updated);
    var provenance = mapping(metadata.provenance || {}, '$.metadata.provenance');
    rejectUnknown(provenance, ['created_by', 'source', 'source_schema_version', 'source_record_id', 'notes'], '$.metadata.provenance');
    return {
      record_id: recordId, schema_version: VERSION, engine_version: VERSION, created_at: created, updated_at: updated,
      status: enumValue(metadata.status, '$.metadata.status', RECORD_STATUSES, 'draft'),
      provenance: {
        created_by: text(provenance.created_by, '$.metadata.provenance.created_by', 'self', false) || 'self',
        source: enumValue(provenance.source, '$.metadata.provenance.source', PROVENANCE_SOURCES, 'direct_entry'),
        source_schema_version: text(provenance.source_schema_version, '$.metadata.provenance.source_schema_version', sourceSchemaVersion, false) || sourceSchemaVersion,
        source_record_id: optionalText(provenance.source_record_id), notes: text(provenance.notes, '$.metadata.provenance.notes', '', false)
      }
    };
  }
  function normalizeHumanReview(value, recordStatus) {
    var review = mapping(value || {}, '$.human_review');
    rejectUnknown(review, ['review_status', 'reviewer', 'reviewed_at', 'notes', 'accepted_findings', 'rejected_findings', 'override_state'], '$.human_review');
    var status = enumValue(review.review_status, '$.human_review.review_status', REVIEW_STATUSES, 'not_reviewed');
    var reviewer = optionalText(review.reviewer); var reviewedAt = optionalTimestamp(review.reviewed_at, '$.human_review.reviewed_at');
    var override = optionalText(review.override_state);
    var states = ['stable recovery conditions', 'recoverable with focused support', 'fragile recovery conditions', 'high-friction recovery conditions'];
    if (override && states.indexOf(override) === -1) fail('$.human_review.override_state', 'enum', 'Must be a recognized recovery-condition state or null.', override);
    if (status === 'reviewed' && !reviewedAt) fail('$.human_review.reviewed_at', 'review_lifecycle', 'A reviewed record requires reviewed_at.');
    if (status === 'reviewed' && !reviewer) fail('$.human_review.reviewer', 'review_lifecycle', 'A reviewed record requires a reviewer.');
    if (recordStatus === 'reviewed' && status !== 'reviewed') fail('$.human_review.review_status', 'review_lifecycle', 'A record with status reviewed requires human_review.review_status reviewed.', status);
    return { review_status: status, reviewer: reviewer, reviewed_at: reviewedAt, notes: text(review.notes, '$.human_review.notes', '', false), accepted_findings: stringList(review.accepted_findings, '$.human_review.accepted_findings'), rejected_findings: stringList(review.rejected_findings, '$.human_review.rejected_findings'), override_state: override };
  }
  function normalizeSections(value) {
    var input = mapping(value, '$.input');
    var required = ['context', 'trigger', 'impact', 'pressure', 'constraints', 'supports', 'capacity', 'response', 'learning', 'next_steps'];
    rejectUnknown(input, required, '$.input');
    var missing = required.filter(function (key) { return !Object.prototype.hasOwnProperty.call(input, key); });
    if (missing.length) fail('$.input', 'required', 'Missing section(s): ' + missing.join(', ') + '.', missing);
    var context = mapping(input.context, '$.input.context'); rejectUnknown(context, ['title', 'domain', 'description', 'stakeholders'], '$.input.context');
    var trigger = mapping(input.trigger, '$.input.trigger'); rejectUnknown(trigger, ['summary', 'type', 'occurred_at'], '$.input.trigger');
    var impact = mapping(input.impact, '$.input.impact'); rejectUnknown(impact, ['severity', 'scope', 'description'], '$.input.impact');
    var pressure = mapping(input.pressure, '$.input.pressure'); rejectUnknown(pressure, ['level', 'sources'], '$.input.pressure');
    var constraints = mapping(input.constraints, '$.input.constraints'); rejectUnknown(constraints, ['items'], '$.input.constraints');
    var supports = mapping(input.supports, '$.input.supports'); rejectUnknown(supports, ['level', 'available'], '$.input.supports');
    var capacity = mapping(input.capacity, '$.input.capacity'); rejectUnknown(capacity, ['energy_level', 'clarity_level', 'available_time_hours', 'time_horizon_days'], '$.input.capacity');
    var response = mapping(input.response, '$.input.response'); rejectUnknown(response, ['actions', 'current_strategy'], '$.input.response');
    var learning = mapping(input.learning, '$.input.learning'); rejectUnknown(learning, ['observations', 'assumptions', 'adaptations'], '$.input.learning');
    var next = mapping(input.next_steps, '$.input.next_steps'); rejectUnknown(next, ['actions', 'checkpoint_date', 'success_signal'], '$.input.next_steps');
    return {
      context: { title: text(context.title, '$.input.context.title', '', true), domain: enumValue(context.domain, '$.input.context.domain', DOMAINS, 'project'), description: text(context.description, '$.input.context.description', '', false), stakeholders: stringList(context.stakeholders, '$.input.context.stakeholders') },
      trigger: { summary: text(trigger.summary, '$.input.trigger.summary', '', true), type: enumValue(trigger.type, '$.input.trigger.type', TRIGGER_TYPES, 'setback'), occurred_at: optionalTimestamp(trigger.occurred_at, '$.input.trigger.occurred_at') },
      impact: { severity: clampScale(impact.severity, '$.input.impact.severity'), scope: enumValue(impact.scope, '$.input.impact.scope', IMPACT_SCOPES, 'project'), description: text(impact.description, '$.input.impact.description', '', false) },
      pressure: { level: clampScale(pressure.level, '$.input.pressure.level'), sources: stringList(pressure.sources, '$.input.pressure.sources') },
      constraints: { items: normalizeConstraints(constraints.items, '$.input.constraints.items') },
      supports: { level: clampScale(supports.level, '$.input.supports.level'), available: normalizeSupports(supports.available, '$.input.supports.available') },
      capacity: { energy_level: clampScale(capacity.energy_level, '$.input.capacity.energy_level'), clarity_level: clampScale(capacity.clarity_level, '$.input.capacity.clarity_level'), available_time_hours: nullableNumber(capacity.available_time_hours, '$.input.capacity.available_time_hours'), time_horizon_days: integer(capacity.time_horizon_days, '$.input.capacity.time_horizon_days', 14) },
      response: { actions: normalizeActions(response.actions, '$.input.response.actions', true), current_strategy: text(response.current_strategy, '$.input.response.current_strategy', '', false) },
      learning: { observations: stringList(learning.observations, '$.input.learning.observations'), assumptions: stringList(learning.assumptions, '$.input.learning.assumptions'), adaptations: stringList(learning.adaptations, '$.input.learning.adaptations') },
      next_steps: { actions: normalizeActions(next.actions, '$.input.next_steps.actions', false), checkpoint_date: optionalDate(next.checkpoint_date, '$.input.next_steps.checkpoint_date'), success_signal: text(next.success_signal, '$.input.next_steps.success_signal', '', false) }
    };
  }
  function normalizeProfile(value) {
    var profile = clone(value || DEFAULT_PROFILE); mapping(profile, '$.methodology_profile');
    rejectUnknown(profile, ['profile_id', 'profile_version', 'calculation_spec', 'component_weights', 'thresholds'], '$.methodology_profile');
    var profileId = text(profile.profile_id, '$.methodology_profile.profile_id', '', true);
    var profileVersion = text(profile.profile_version, '$.methodology_profile.profile_version', '', true);
    var spec = text(profile.calculation_spec, '$.methodology_profile.calculation_spec', '', true);
    if (spec !== 'weighted-components-v1') fail('$.methodology_profile.calculation_spec', 'calculation_spec', 'Only weighted-components-v1 is supported.', spec);
    var expected = Object.keys(DEFAULT_PROFILE.component_weights); var weightsMap = mapping(profile.component_weights, '$.methodology_profile.component_weights');
    rejectUnknown(weightsMap, expected, '$.methodology_profile.component_weights');
    var weights = {}; var total = 0;
    expected.forEach(function (key) { if (!Object.prototype.hasOwnProperty.call(weightsMap, key)) fail('$.methodology_profile.component_weights', 'required', 'Missing component weight(s): ' + key + '.', [key]); var number = Number(weightsMap[key]); if (Number.isNaN(number)) fail('$.methodology_profile.component_weights.' + key, 'numeric_required', 'Must be numeric.', weightsMap[key]); if (number < 0) fail('$.methodology_profile.component_weights.' + key, 'minimum', 'Must be zero or greater.', number); weights[key] = number; total += number; });
    if (Math.abs(total - 100) > 0.000001) fail('$.methodology_profile.component_weights', 'weight_total', 'Component weights must total 100.', total);
    var thresholdsMap = mapping(profile.thresholds, '$.methodology_profile.thresholds'); var keys = ['stable', 'focused_support', 'fragile']; rejectUnknown(thresholdsMap, keys, '$.methodology_profile.thresholds');
    var thresholds = {}; keys.forEach(function (key) { if (!Object.prototype.hasOwnProperty.call(thresholdsMap, key)) fail('$.methodology_profile.thresholds', 'required', 'Missing threshold(s): ' + key + '.', [key]); var number = Number(thresholdsMap[key]); if (Number.isNaN(number)) fail('$.methodology_profile.thresholds.' + key, 'numeric_required', 'Must be numeric.', thresholdsMap[key]); if (number < 0 || number > 100) fail('$.methodology_profile.thresholds.' + key, 'range', 'Must be between 0 and 100.', number); thresholds[key] = number; });
    if (!(thresholds.stable > thresholds.focused_support && thresholds.focused_support > thresholds.fragile)) fail('$.methodology_profile.thresholds', 'threshold_order', 'Thresholds must descend: stable > focused_support > fragile.', thresholds);
    return { profile_id: profileId, profile_version: profileVersion, calculation_spec: spec, component_weights: weights, thresholds: thresholds };
  }
  function normalizeInput(data) {
    if (!isObject(data)) fail('$', 'type_error', 'Input must be an object.', data);
    var migrated = Object.prototype.hasOwnProperty.call(data, 'challenge') && !Object.prototype.hasOwnProperty.call(data, 'input');
    var request = migrated ? migrateV1Request(data) : clone(data);
    rejectUnknown(request, ['metadata', 'input', 'human_review', 'extensions', 'methodology_profile'], '$');
    if (!request.input) fail('$.input', 'required', 'The input object is required.');
    var sourceSchema = migrated ? '1.0.1' : String((request.metadata && (request.metadata.schema_version || (request.metadata.provenance && request.metadata.provenance.source_schema_version))) || VERSION);
    var metadata = normalizeMetadata(request.metadata, sourceSchema);
    return { metadata: metadata, input: normalizeSections(request.input), human_review: normalizeHumanReview(request.human_review, metadata.status), extensions: normalizeExtensions(request.extensions), methodology_profile: normalizeProfile(request.methodology_profile), migrated: migrated, user_input: clone(request.input) };
  }
  function positive(value) { return Math.max(0, Math.min(1, (value - 1) / 9)); }
  function inverse(value) { return Math.max(0, Math.min(1, (10 - value) / 9)); }
  function constraintManageability(items) { if (!items.length) return 1; var values = { controllable: 1, influence: 0.65, limited: 0.25, unknown: 0.4 }; return items.reduce(function (sum, item) { return sum + values[item.controllability]; }, 0) / items.length; }
  function actionReadiness(input) { var titles = []; input.response.actions.concat(input.next_steps.actions).forEach(function (action) { var title = action.title.trim().toLowerCase(); if (title && titles.indexOf(title) === -1) titles.push(title); }); return [Math.min(1, titles.length / 4), titles.length]; }
  function calculateComponentScores(input, profile) {
    var ready = actionReadiness(input); var raw = {
      impact_buffer: [input.impact.severity, inverse(input.impact.severity), 'Lower recorded impact leaves more near-term recovery room; severity remains visible separately.'],
      pressure_buffer: [input.pressure.level, inverse(input.pressure.level), 'Lower recorded pressure increases the room available for deliberate recovery action.'],
      energy_capacity: [input.capacity.energy_level, positive(input.capacity.energy_level), 'Recorded energy is treated as available capacity, not motivation or character.'],
      support_capacity: [input.supports.level, positive(input.supports.level), 'Recorded access to support increases recovery capacity.'],
      clarity_capacity: [input.capacity.clarity_level, positive(input.capacity.clarity_level), 'Recorded clarity supports prioritization and a bounded next step.'],
      action_readiness: [ready[1], ready[0], 'Readiness increases with up to four distinct response or next-step actions.'],
      constraint_manageability: [input.constraints.items.length, constraintManageability(input.constraints.items), 'Manageability reflects the recorded controllability of constraints; no listed constraints defaults to full manageability.']
    };
    var scores = {}; Object.keys(profile.component_weights).forEach(function (key) { var weight = Number(profile.component_weights[key]); scores[key] = { input_value: raw[key][0], normalized_value: round(raw[key][1], 4), weight: weight, weighted_score: round(raw[key][1] * weight, 1), explanation: raw[key][2] }; }); return scores;
  }
  function stateFromScore(score, profile) { var thresholds = normalizeProfile(profile).thresholds; if (score >= thresholds.stable) return 'stable recovery conditions'; if (score >= thresholds.focused_support) return 'recoverable with focused support'; if (score >= thresholds.fragile) return 'fragile recovery conditions'; return 'high-friction recovery conditions'; }
  function buildFlags(input) {
    var flags = []; function add(code, severity, section, message, rationale) { flags.push({ code: code, severity: severity, section: section, message: message, rationale: rationale }); }
    if (input.impact.severity >= 8) add('high_impact', 'high', 'impact', 'Reduce scope and protect recovery time.', 'Impact severity is recorded at 8 or above.');
    if (input.pressure.level >= 8) add('high_pressure', 'high', 'pressure', 'Clarify what can pause, wait, or be delegated.', 'Pressure is recorded at 8 or above.');
    if (input.capacity.energy_level <= 3) add('low_energy_capacity', 'high', 'capacity', 'Avoid overloading the next action plan.', 'Energy capacity is recorded at 3 or below.');
    if (input.supports.level <= 3) add('low_support_capacity', 'high', 'supports', 'Identify one concrete support channel before expanding work.', 'Support capacity is recorded at 3 or below.');
    if (input.capacity.clarity_level <= 3) add('low_clarity_capacity', 'high', 'capacity', 'Define the decision, owner, and next checkpoint.', 'Clarity is recorded at 3 or below.');
    if (input.capacity.time_horizon_days <= 3) add('short_horizon', 'medium', 'capacity', 'Choose a recovery action that can be completed quickly.', 'The time horizon is three days or less.');
    var limited = input.constraints.items.filter(function (item) { return item.controllability === 'limited'; }).length;
    if (limited >= 2) add('limited_constraints', 'medium', 'constraints', 'Separate controllable work from constraints that require escalation or accommodation.', 'Two or more constraints are recorded as having limited controllability.');
    return flags;
  }
  function buildNextActions(input) {
    var output = []; var seen = {};
    function add(code, title, rationale, source, priority) { var key = title.trim().toLowerCase(); if (key && !seen[key] && output.length < 6) { seen[key] = true; output.push({ code: code, title: title, rationale: rationale, source: source, priority: priority }); } }
    input.next_steps.actions.concat(input.response.actions).forEach(function (action, index) { add('user_action_' + (index + 1), action.title, 'Preserved from the recorded response or next-step plan.', 'user', index === 0 ? 'high' : 'medium'); });
    if (input.capacity.clarity_level <= 5) add('define_recovery', 'Write a one-sentence definition of recovery for this situation.', 'Clarity is at or below the midpoint.', 'engine', 'high');
    if (input.supports.level <= 5) add('request_support', 'Ask for one specific form of support or remove one friction point.', 'Support is at or below the midpoint.', 'engine', 'high');
    if (input.pressure.level >= 7) add('bound_checkpoint', 'Reduce the work to one near-term checkpoint instead of a full reset.', 'Pressure is elevated.', 'engine', 'high');
    if (input.constraints.items.length) add('map_constraints', 'Mark each constraint as controllable, influenceable, or limited.', 'Recorded constraints should be routed differently based on controllability.', 'engine', 'medium');
    if (!output.length) DEFAULT_ACTIONS.forEach(function (title, index) { add('default_action_' + (index + 1), title, 'Default recovery-planning prompt.', 'engine', 'medium'); });
    return output;
  }
  function generateRecord(data, methodologyProfile) {
    var canonical = normalizeInput(data); var input = canonical.input; var profile = normalizeProfile(methodologyProfile || canonical.methodology_profile);
    var components = calculateComponentScores(input, profile); var total = 0; Object.keys(components).forEach(function (key) { total += components[key].normalized_value * components[key].weight; }); var score = round(total, 1);
    var generatedState = stateFromScore(score, profile); var override = canonical.human_review.override_state; var effective = override || generatedState;
    return {
      metadata: canonical.metadata,
      user_input: canonical.user_input,
      normalized_input: input,
      findings: {
        methodology: profile, component_scores: components, recovery_score: score, generated_state: generatedState, effective_state: effective,
        human_override_applied: Boolean(override), flags: buildFlags(input), recommended_actions: buildNextActions(input),
        decision_note: 'Recorded recovery conditions are assessed as ' + generatedState + ' with a conditions score of ' + score + '/100. Review the component explanations, protect available capacity, address the highest-friction condition, and update the record at the next checkpoint.',
        method_path: METHOD_PATH.slice(), interpretation_limits: INTERPRETATION_LIMITS.slice(),
        calculation_provenance: { schema_version: VERSION, engine_version: VERSION, profile_id: profile.profile_id, profile_version: profile.profile_version, calculated_at: canonical.metadata.updated_at }
      },
      human_review: canonical.human_review,
      extensions: canonical.extensions
    };
  }

  function lines(value) { return String(value || '').split('\n').map(function (item) { return item.trim(); }).filter(Boolean); }
  function collect(form) {
    var now = nowISO();
    return {
      metadata: { record_id: form.dataset.recordId || randomRecordId(), created_at: form.dataset.createdAt || now, updated_at: now, status: form.record_status.value, provenance: { created_by: 'browser user', source: 'browser', source_schema_version: VERSION, source_record_id: null, notes: '' } },
      input: {
        context: { title: form.title.value, domain: form.domain.value, description: form.description.value, stakeholders: lines(form.stakeholders.value) },
        trigger: { summary: form.trigger_summary.value, type: form.trigger_type.value, occurred_at: null },
        impact: { severity: form.impact_severity.value, scope: form.impact_scope.value, description: form.impact_description.value },
        pressure: { level: form.pressure_level.value, sources: lines(form.pressure_sources.value) },
        constraints: { items: lines(form.constraints.value) }, supports: { level: form.support_level.value, available: lines(form.supports_available.value) },
        capacity: { energy_level: form.energy_level.value, clarity_level: form.clarity_level.value, available_time_hours: form.available_time_hours.value, time_horizon_days: form.time_horizon_days.value },
        response: { actions: lines(form.response_actions.value), current_strategy: form.current_strategy.value },
        learning: { observations: lines(form.learning_observations.value), assumptions: lines(form.learning_assumptions.value), adaptations: lines(form.learning_adaptations.value) },
        next_steps: { actions: lines(form.next_actions.value), checkpoint_date: form.checkpoint_date.value || null, success_signal: form.success_signal.value }
      },
      human_review: { review_status: form.review_status.value, reviewer: null, reviewed_at: null, notes: '', accepted_findings: [], rejected_findings: [], override_state: null },
      extensions: {}
    };
  }
  function list(element, items, formatter, fallback) { element.innerHTML = ''; (items.length ? items : [fallback]).forEach(function (item) { var li = document.createElement('li'); li.textContent = typeof item === 'string' ? item : formatter(item); element.appendChild(li); }); }
  function renderComponents(element, components) { element.innerHTML = ''; Object.keys(components).forEach(function (key) { var item = components[key]; var row = document.createElement('li'); row.innerHTML = '<strong></strong><span></span><small></small>'; row.querySelector('strong').textContent = key.replace(/_/g, ' '); row.querySelector('span').textContent = item.weighted_score + '/' + item.weight; row.querySelector('small').textContent = item.explanation; element.appendChild(row); }); }
  function showError(widget, error) { var panel = widget.querySelector('[data-cg-errors]'); panel.hidden = false; var payload = error instanceof ValidationError ? error.toJSON() : { issues: [{ path: '$', message: error.message || String(error) }] }; list(panel.querySelector('ul'), payload.issues, function (item) { return item.path + ': ' + item.message; }, 'Unknown validation error.'); }
  function clearError(widget) { widget.querySelector('[data-cg-errors]').hidden = true; }
  function render(widget) {
    clearError(widget);
    try {
      var output = generateRecord(collect(widget.querySelector('[data-cg-form]'))); var form = widget.querySelector('[data-cg-form]'); form.dataset.recordId = output.metadata.record_id; form.dataset.createdAt = output.metadata.created_at;
      widget.querySelector('[data-cg-score]').textContent = output.findings.recovery_score + '/100'; widget.querySelector('[data-cg-state]').textContent = output.findings.generated_state;
      widget.querySelector('[data-cg-profile]').textContent = output.findings.methodology.profile_id + ' v' + output.findings.methodology.profile_version;
      renderComponents(widget.querySelector('[data-cg-components]'), output.findings.component_scores);
      list(widget.querySelector('[data-cg-flags]'), output.findings.flags, function (item) { return item.severity.toUpperCase() + ' · ' + item.section + ': ' + item.message; }, 'No major review flags generated.');
      list(widget.querySelector('[data-cg-actions]'), output.findings.recommended_actions, function (item) { return item.priority.toUpperCase() + ': ' + item.title + ' — ' + item.rationale; }, 'No actions generated.');
      widget.querySelector('[data-cg-note]').textContent = output.findings.decision_note; widget.querySelector('[data-cg-json]').textContent = JSON.stringify(output, null, 2); widget._cgOutput = output; return output;
    } catch (error) { showError(widget, error); throw error; }
  }
  function download(widget) { var output = widget._cgOutput || render(widget); var blob = new Blob([JSON.stringify(output, null, 2)], { type: 'application/json' }); var url = URL.createObjectURL(blob); var link = document.createElement('a'); link.href = url; link.download = output.metadata.record_id + '.json'; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url); }
  function initialize() {
    if (typeof document === 'undefined') return;
    document.querySelectorAll('.cg-demo').forEach(function (widget) {
      widget.querySelectorAll('input[type="range"]').forEach(function (input) { var output = widget.querySelector('[data-out="' + input.name + '"]'); input.addEventListener('input', function () { output.textContent = input.value; }); });
      widget.querySelector('[data-cg-generate]').addEventListener('click', function () { try { render(widget); } catch (error) {} });
      widget.querySelector('[data-cg-download]').addEventListener('click', function () { try { download(widget); } catch (error) {} });
    });
  }
  if (typeof document !== 'undefined') { if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize); else initialize(); }
  return { VERSION: VERSION, DEFAULT_PROFILE: clone(DEFAULT_PROFILE), ValidationError: ValidationError, migrateV1Request: migrateV1Request, normalizeInput: normalizeInput, normalizeProfile: normalizeProfile, calculateComponentScores: calculateComponentScores, stateFromScore: stateFromScore, buildFlags: buildFlags, buildNextActions: buildNextActions, generateRecord: generateRecord };
});
