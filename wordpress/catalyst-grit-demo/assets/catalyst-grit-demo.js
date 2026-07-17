(function (root, factory) {
  var engine = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = engine;
  }
  if (root) {
    root.CatalystGritEngine = engine;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var VERSION = '1.0.1';
  var METHOD_PATH = ['setback', 'context', 'impact', 'pressure', 'support', 'response', 'recovery pattern', 'next action', 'review'];
  var DEFAULT_ACTIONS = ['Name the smallest recoverable next step', 'Review support and constraints', 'Schedule a short follow-up review'];

  function clamp(value, low, high) {
    var number = Number(value);
    if (Number.isNaN(number)) {
      throw new TypeError('scale values must be numeric');
    }
    return Math.max(low, Math.min(high, number));
  }

  function cleanActions(value) {
    var source = Array.isArray(value) ? value : String(value || '').split('\n');
    var actions = source.map(function (item) { return String(item).trim(); }).filter(Boolean);
    return actions.length ? actions : DEFAULT_ACTIONS.slice();
  }

  function normalizeInput(data) {
    var input = data || {};
    var domain = String(input.domain || 'project').trim() || 'project';
    var reviewStatus = String(input.review_status || 'draft').trim() || 'draft';
    var domains = ['work', 'learning', 'health_wellbeing', 'relationship', 'project', 'career', 'other'];
    var statuses = ['draft', 'needs_review', 'reviewed'];
    if (domains.indexOf(domain) === -1) throw new TypeError('unsupported domain');
    if (statuses.indexOf(reviewStatus) === -1) throw new TypeError('unsupported review_status');
    var horizon = Math.max(1, Math.trunc(Number(input.time_horizon_days == null ? 14 : input.time_horizon_days)));
    if (Number.isNaN(horizon)) throw new TypeError('time_horizon_days must be numeric');
    return {
      challenge: String(input.challenge || '').trim() || 'Unspecified challenge',
      domain: domain,
      impact_severity: clamp(input.impact_severity == null ? 5 : input.impact_severity, 1, 10),
      pressure_level: clamp(input.pressure_level == null ? 5 : input.pressure_level, 1, 10),
      energy_level: clamp(input.energy_level == null ? 5 : input.energy_level, 1, 10),
      support_level: clamp(input.support_level == null ? 5 : input.support_level, 1, 10),
      clarity_level: clamp(input.clarity_level == null ? 5 : input.clarity_level, 1, 10),
      recovery_actions: cleanActions(input.recovery_actions),
      time_horizon_days: horizon,
      review_status: reviewStatus
    };
  }

  function recoveryScore(record) {
    var bonus = Math.min(10, record.recovery_actions.length * 2.5);
    var raw = record.energy_level * 2.2 + record.support_level * 2.3 + record.clarity_level * 2.4 + bonus + (10 - record.impact_severity) * 1.7 + (10 - record.pressure_level) * 1.4;
    return Math.round(Math.max(0, Math.min(100, raw)) * 10) / 10;
  }

  function stateFromScore(score) {
    if (score >= 76) return 'stable recovery conditions';
    if (score >= 56) return 'recoverable with focused support';
    if (score >= 36) return 'fragile recovery conditions';
    return 'high-friction recovery conditions';
  }

  function buildFlags(record) {
    var flags = [];
    if (record.impact_severity >= 8) flags.push('High impact severity: reduce scope and protect recovery time.');
    if (record.pressure_level >= 8) flags.push('High pressure: clarify what can pause, wait, or be delegated.');
    if (record.energy_level <= 3) flags.push('Low energy: avoid overloading the next action plan.');
    if (record.support_level <= 3) flags.push('Low support: identify one concrete support channel before expanding work.');
    if (record.clarity_level <= 3) flags.push('Low clarity: define the decision, owner, and next checkpoint.');
    if (record.time_horizon_days <= 3) flags.push('Very short horizon: choose a recovery action that can be completed quickly.');
    return flags;
  }

  function buildNextActions(record) {
    var actions = record.recovery_actions.slice(0, 4);
    if (record.clarity_level <= 5) actions.push('Write a one-sentence definition of what recovery means for this situation.');
    if (record.support_level <= 5) actions.push('Ask for one specific form of support or remove one friction point.');
    if (record.pressure_level >= 7) actions.push('Reduce the work to one near-term checkpoint instead of a full reset.');
    return actions.slice(0, 6);
  }

  function generateRecord(data) {
    var record = normalizeInput(data);
    var score = recoveryScore(record);
    var state = stateFromScore(score);
    var note = 'Recovery conditions are assessed as ' + state + ' with a score of ' + score + '/100. Use this as a structured reflection record: clarify the next action, protect recovery capacity, review support, and update the plan after the next checkpoint.';
    return Object.assign({}, record, {
      recovery_score: score,
      resilience_state: state,
      risk_flags: buildFlags(record),
      next_actions: buildNextActions(record),
      decision_note: note,
      method_path: METHOD_PATH.slice(),
      schema_version: VERSION,
      engine_version: VERSION
    });
  }

  function list(element, items, fallback) {
    element.innerHTML = '';
    (items.length ? items : [fallback]).forEach(function (item) {
      var li = document.createElement('li');
      li.textContent = item;
      element.appendChild(li);
    });
  }

  function collect(form) {
    return {
      challenge: form.challenge.value,
      domain: form.domain.value,
      impact_severity: form.impact_severity.value,
      pressure_level: form.pressure_level.value,
      energy_level: form.energy_level.value,
      support_level: form.support_level.value,
      clarity_level: form.clarity_level.value,
      recovery_actions: form.recovery_actions.value,
      time_horizon_days: form.time_horizon_days.value,
      review_status: form.review_status.value
    };
  }

  function render(widget) {
    var output = generateRecord(collect(widget.querySelector('[data-cg-form]')));
    widget.querySelector('[data-cg-score]').textContent = output.recovery_score + '/100';
    widget.querySelector('[data-cg-state]').textContent = output.resilience_state;
    list(widget.querySelector('[data-cg-flags]'), output.risk_flags, 'No major review flags generated.');
    list(widget.querySelector('[data-cg-actions]'), output.next_actions, 'No next actions generated.');
    widget.querySelector('[data-cg-note]').textContent = output.decision_note;
    widget.querySelector('[data-cg-json]').textContent = JSON.stringify(output, null, 2);
    widget._cgOutput = output;
    return output;
  }

  function download(widget) {
    var output = widget._cgOutput || render(widget);
    var blob = new Blob([JSON.stringify(output, null, 2)], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var link = document.createElement('a');
    link.href = url;
    link.download = 'catalyst-grit-record.json';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function initialize() {
    if (typeof document === 'undefined') return;
    document.querySelectorAll('.cg-demo').forEach(function (widget) {
      widget.querySelectorAll('input[type="range"]').forEach(function (input) {
        var output = widget.querySelector('[data-out="' + input.name + '"]');
        input.addEventListener('input', function () { if (output) output.textContent = input.value; });
      });
      widget.querySelector('[data-cg-generate]').addEventListener('click', function () { render(widget); });
      widget.querySelector('[data-cg-download]').addEventListener('click', function () { download(widget); });
      render(widget);
    });
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize);
    else initialize();
  }

  return {
    VERSION: VERSION,
    METHOD_PATH: METHOD_PATH.slice(),
    normalizeInput: normalizeInput,
    recoveryScore: recoveryScore,
    stateFromScore: stateFromScore,
    buildFlags: buildFlags,
    buildNextActions: buildNextActions,
    generateRecord: generateRecord
  };
});
