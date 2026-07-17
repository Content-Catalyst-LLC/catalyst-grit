<?php
/**
 * Plugin Name: Catalyst Grit Demo
 * Description: Canonical public recovery-record demo and authenticated private workspace. Provides [catalyst_grit_demo] and [catalyst_grit_workspace].
 * Version: 1.4.0
 * Author: Content Catalyst LLC
 * License: MIT
 */

if (!defined('ABSPATH')) { exit; }

define('CATALYST_GRIT_DEMO_VERSION', '1.4.0');

function catalyst_grit_demo_assets() {
    $base = plugin_dir_url(__FILE__);
    wp_enqueue_style('catalyst-grit-demo', $base . 'assets/catalyst-grit-demo.css', array(), CATALYST_GRIT_DEMO_VERSION);
    wp_enqueue_script('catalyst-grit-demo', $base . 'assets/catalyst-grit-demo.js', array(), CATALYST_GRIT_DEMO_VERSION, true);
}
add_action('wp_enqueue_scripts', 'catalyst_grit_demo_assets');

function catalyst_grit_demo_shortcode() {
    ob_start();
    ?>
    <section class="cg-demo" aria-labelledby="cg-demo-title" data-cg-version="<?php echo esc_attr(CATALYST_GRIT_DEMO_VERSION); ?>">
      <header class="cg-demo__header">
        <p class="cg-demo__eyebrow">Catalyst Grit · Canonical contract v<?php echo esc_html(CATALYST_GRIT_DEMO_VERSION); ?></p>
        <h3 id="cg-demo-title">Build a Recovery Record</h3>
        <p>Document the context, trigger, recovery conditions, response, learning, and an executable recovery plan. The shared engine returns pressure, constraint, support, capacity, control-zone, and friction-layer maps alongside owned actions, planning horizons, dependencies, blockers, escalation paths, a dated checkpoint, explainable components, provenance, and portable JSON.</p>
      </header>
      <div class="cg-demo__errors" data-cg-errors role="alert" tabindex="-1" hidden>
        <h4>Review these fields</h4><ul></ul>
      </div>
      <div class="cg-demo__grid">
        <form class="cg-demo__form" data-cg-form novalidate>
          <fieldset><legend>Record and context</legend>
            <div class="cg-demo__two">
              <label><span>Record status</span><select name="record_status"><option value="draft">Draft</option><option value="active">Active</option><option value="under_review">Under review</option></select></label>
              <label><span>Human review</span><select name="review_status"><option value="not_reviewed">Not reviewed</option><option value="needs_review">Needs review</option><option value="in_review">In review</option></select></label>
            </div>
            <label><span>Record title</span><input name="title" required value="Sustainability reporting project recovery"></label>
            <label><span>Context</span><textarea name="description" rows="3">The workstream lost momentum after conflicting stakeholder feedback and a missed checkpoint.</textarea></label>
            <div class="cg-demo__two">
              <label><span>Domain</span><select name="domain"><option value="project">Project</option><option value="work">Work</option><option value="career">Career</option><option value="learning">Learning</option><option value="organization">Organization</option><option value="community">Community</option><option value="relationship">Relationship</option><option value="health_wellbeing">Health / wellbeing</option><option value="other">Other</option></select></label>
              <label><span>Trigger type</span><select name="trigger_type"><option value="delay">Delay</option><option value="setback">Setback</option><option value="conflict">Conflict</option><option value="constraint_change">Constraint change</option><option value="capacity_change">Capacity change</option><option value="external_event">External event</option><option value="other">Other</option></select></label>
            </div>
            <label><span>Trigger summary</span><textarea name="trigger_summary" rows="2" required>Conflicting feedback changed the expected deliverable after the checkpoint was missed.</textarea></label>
            <label><span>Stakeholders, one per line</span><textarea name="stakeholders" rows="2">project lead
reporting team
reviewers</textarea></label>
            <label><span>Affected work, decisions, or relationships, one per line</span><textarea name="affected_work" rows="2">publication timeline
approval decision
review workflow</textarea></label>
          </fieldset>

          <fieldset><legend>Impact, pressure, supports, and capacity</legend>
            <div class="cg-demo__sliders">
              <label><span>Impact severity <strong data-out="impact_severity">7</strong>/10</span><input type="range" name="impact_severity" min="1" max="10" value="7"></label>
              <label><span>Pressure level <strong data-out="pressure_level">8</strong>/10</span><input type="range" name="pressure_level" min="1" max="10" value="8"></label>
              <label><span>Energy capacity <strong data-out="energy_level">5</strong>/10</span><input type="range" name="energy_level" min="1" max="10" value="5"></label>
              <label><span>Support capacity <strong data-out="support_level">6</strong>/10</span><input type="range" name="support_level" min="1" max="10" value="6"></label>
              <label><span>Clarity capacity <strong data-out="clarity_level">4</strong>/10</span><input type="range" name="clarity_level" min="1" max="10" value="4"></label>
            </div>
            <div class="cg-demo__two">
              <label><span>Impact scope</span><select name="impact_scope"><option value="project">Project</option><option value="task">Task</option><option value="workstream">Workstream</option><option value="team">Team</option><option value="organization">Organization</option><option value="personal">Personal</option><option value="multi_system">Multi-system</option><option value="other">Other</option></select></label>
              <label><span>Time horizon (days)</span><input type="number" name="time_horizon_days" min="1" value="14"></label>
            </div>
            <label><span>Impact description</span><textarea name="impact_description" rows="2">The publication timeline moved and ownership became unclear.</textarea></label>
            <label><span>Pressure sources, one per line</span><textarea name="pressure_sources" rows="2">publication deadline
stakeholder disagreement</textarea></label>
            <label><span>Competing demands, one per line</span><textarea name="competing_demands" rows="2">parallel publication work
reviewer availability</textarea></label>
            <div class="cg-demo__sliders">
              <label><span>Decision ambiguity <strong data-out="decision_ambiguity">7</strong>/10</span><input type="range" name="decision_ambiguity" min="1" max="10" value="7"></label>
              <label><span>Dependency friction <strong data-out="dependency_friction">8</strong>/10</span><input type="range" name="dependency_friction" min="1" max="10" value="8"></label>
              <label><span>Stakeholder friction <strong data-out="stakeholder_friction">7</strong>/10</span><input type="range" name="stakeholder_friction" min="1" max="10" value="7"></label>
              <label><span>Attention capacity <strong data-out="attention_level">5</strong>/10</span><input type="range" name="attention_level" min="1" max="10" value="5"></label>
              <label><span>Coordination capacity <strong data-out="coordination_capacity">5</strong>/10</span><input type="range" name="coordination_capacity" min="1" max="10" value="5"></label>
              <label><span>Competing load <strong data-out="load_level">8</strong>/10</span><input type="range" name="load_level" min="1" max="10" value="8"></label>
            </div>
            <label><span>Constraints, one per line</span><textarea name="constraints" rows="2">Final approval dependency
Limited review window</textarea></label>
            <label><span>Available supports, one per line</span><textarea name="supports_available" rows="2">Project lead
Decision log</textarea></label>
            <div class="cg-demo__two">
              <label><span>Available time (hours)</span><input type="number" name="available_time_hours" min="0" value="12"></label>
              <label><span>Protected recovery time (hours)</span><input type="number" name="recovery_time_hours" min="0" value="4"></label>
            </div>
          </fieldset>

          <fieldset><legend>Response, learning, and next steps</legend>
            <label><span>Current strategy</span><textarea name="current_strategy" rows="2">Reduce scope to the decision needed for the next checkpoint.</textarea></label>
            <label><span>Response actions, one per line</span><textarea name="response_actions" rows="3">Clarify the next decision owner
Break the work into a 48-hour recovery task</textarea></label>
            <label><span>Observations, one per line</span><textarea name="learning_observations" rows="2">Feedback arrived through multiple channels.</textarea></label>
            <label><span>Assumptions, one per line</span><textarea name="learning_assumptions" rows="2">The final decision owner was understood by everyone.</textarea></label>
            <label><span>Adaptations, one per line</span><textarea name="learning_adaptations" rows="2">Record the decision owner before the next review cycle.</textarea></label>
            <label><span>Next actions, one per line</span><textarea name="next_actions" rows="3">Document unresolved assumptions
Schedule a short stakeholder review</textarea></label>
            <div class="cg-demo__two">
              <label><span>Default action owner</span><input name="action_owner" value="project lead"></label>
              <label><span>Smallest-step target date</span><input type="date" name="action_target_date"></label>
            </div>
            <div class="cg-demo__two">
              <label><span>Scope decision</span><select name="scope_decision"><option value="continue">Continue</option><option value="reduce_scope" selected>Reduce scope</option><option value="pause">Pause</option><option value="delegate">Delegate</option><option value="escalate">Escalate</option></select></label>
              <label><span>First planning horizon</span><select name="action_horizon"><option value="24_hours" selected>24 hours</option><option value="72_hours">72 hours</option><option value="7_days">7 days</option><option value="longer_term">Longer term</option></select></label>
            </div>
            <label><span>Scope decision notes</span><textarea name="scope_decision_notes" rows="2">Limit recovery work to the decision and evidence needed for the next checkpoint.</textarea></label>
            <label><span>Known blockers, one per line</span><textarea name="blockers" rows="2">External reviewer availability may constrain the checkpoint.</textarea></label>
            <label><span>Escalation paths, one per line</span><textarea name="escalation_log" rows="2">Escalate unresolved decision ownership to the program sponsor after 24 hours.</textarea></label>
            <div class="cg-demo__two">
              <label><span>Checkpoint date</span><input type="date" name="checkpoint_date"></label>
              <label><span>Success signal</span><input name="success_signal" value="One owner, one approved scope, and a dated checkpoint."></label>
            </div>
            <label><span>Reassessment trigger</span><input name="reassessment_trigger" value="Reassess at the checkpoint or sooner if the approval dependency changes."></label>
          </fieldset>
          <div class="cg-demo__actions"><button type="button" data-cg-generate>Generate record</button><button type="button" data-cg-download>Download JSON</button></div>
        </form>

        <div class="cg-demo__output" aria-live="polite">
          <div class="cg-demo__score"><span>Conditions score · component context required</span><strong data-cg-score>—</strong></div>
          <div class="cg-demo__panel"><h4>Generated state</h4><p data-cg-state>Generate a record to view the recovery conditions.</p><p class="cg-demo__method">Method: <span data-cg-profile>cg-recovery-conditions v1.4.0</span></p><p><strong>Completeness:</strong> <span data-cg-completeness>—</span> · <strong>Confidence:</strong> <span data-cg-confidence>—</span></p></div>
          <div class="cg-demo__panel"><h4>Pressure map</h4><ul data-cg-pressure-map><li>Generate a record to map pressure.</li></ul></div>
          <div class="cg-demo__panel"><h4>Constraint map</h4><ul data-cg-constraint-map><li>Generate a record to map constraints.</li></ul></div>
          <div class="cg-demo__panel"><h4>Support map</h4><ul data-cg-support-map><li>Generate a record to map supports.</li></ul></div>
          <div class="cg-demo__panel cg-demo__panel--plan"><h4>Executable recovery plan</h4><p data-cg-plan-summary>Generate a record to identify the smallest recoverable next step.</p><p class="cg-demo__method"><strong>Checkpoint:</strong> <span data-cg-plan-checkpoint>—</span> · <strong>Scope:</strong> <span data-cg-plan-scope>—</span></p></div>
          <div class="cg-demo__panel"><h4>Planning horizons</h4><ul data-cg-plan-horizons><li>Generate a record to sequence actions.</li></ul></div>
          <div class="cg-demo__panel"><h4>Blockers, escalation, and review signals</h4><ul data-cg-plan-signals><li>Generate a record to inspect support needs.</li></ul></div>
          <div class="cg-demo__panel"><h4>Missing-context prompts</h4><ul data-cg-missing><li>Generate a record to inspect completeness.</li></ul></div>
          <div class="cg-demo__panel"><h4>Contradictions</h4><ul data-cg-contradictions><li>Generate a record to inspect contradictions.</li></ul></div>
          <div class="cg-demo__panel"><h4>Component explanations</h4><ul class="cg-demo__components" data-cg-components><li>Generate a record to view weighted components.</li></ul></div>
          <div class="cg-demo__panel"><h4>Review flags</h4><ul data-cg-flags><li>No flags generated yet.</li></ul></div>
          <div class="cg-demo__panel"><h4>Recommended actions</h4><ul data-cg-actions><li>No actions generated yet.</li></ul></div>
          <div class="cg-demo__panel"><h4>Decision note</h4><p data-cg-note>Use the form to generate a structured recovery note.</p></div>
          <details class="cg-demo__json"><summary>Canonical JSON export</summary><pre data-cg-json>{}</pre></details>
        </div>
      </div>
      <p class="cg-demo__disclaimer">Educational and analytical infrastructure only. This record describes recovery conditions, not character. It is not diagnosis, mental-health advice, employee evaluation, ranking, automated eligibility, or an outcome guarantee. Inputs remain in the browser unless exported.</p>
    </section>
    <?php
    return ob_get_clean();
}
add_shortcode('catalyst_grit_demo', 'catalyst_grit_demo_shortcode');


/**
 * Authenticated private workspace. This surface is intentionally separate from
 * the public client-side demo and stores only in the current user's private
 * WordPress user metadata.
 */
function catalyst_grit_workspace_shortcode() {
    if (!is_user_logged_in()) {
        return '<section class="cg-workspace cg-workspace--locked"><h3>Private Catalyst Grit Workspace</h3><p>You must be signed in to open this private workspace.</p></section>';
    }
    if (!current_user_can('read')) {
        return '<section class="cg-workspace cg-workspace--locked"><h3>Private Catalyst Grit Workspace</h3><p>Your account is not authorized to use this workspace.</p></section>';
    }
    $base = plugin_dir_url(__FILE__);
    wp_enqueue_style('catalyst-grit-workspace', $base . 'assets/catalyst-grit-workspace.css', array(), CATALYST_GRIT_DEMO_VERSION);
    wp_enqueue_script('catalyst-grit-workspace', $base . 'assets/catalyst-grit-workspace.js', array(), CATALYST_GRIT_DEMO_VERSION, true);
    wp_localize_script('catalyst-grit-workspace', 'CatalystGritWorkspace', array(
        'ajaxUrl' => admin_url('admin-ajax.php'),
        'nonce' => wp_create_nonce('catalyst_grit_workspace_v140'),
        'version' => CATALYST_GRIT_DEMO_VERSION,
        'maxBytes' => 524288,
    ));
    ob_start();
    ?>
    <section class="cg-workspace" data-cg-workspace data-cg-visibility="private" aria-labelledby="cg-workspace-title">
      <header>
        <p class="cg-workspace__eyebrow">Catalyst Grit · Authenticated workspace v<?php echo esc_html(CATALYST_GRIT_DEMO_VERSION); ?></p>
        <h3 id="cg-workspace-title">Private Recovery Workspace</h3>
        <p>Save private project and record bundles to your own WordPress account. This workspace is not exposed by the public demo shortcode.</p>
      </header>
      <div class="cg-workspace__status" data-cg-workspace-status role="status" aria-live="polite">Workspace ready.</div>
      <label class="cg-workspace__field"><span>Workspace JSON</span>
        <textarea rows="18" data-cg-workspace-json spellcheck="false" aria-describedby="cg-workspace-help"></textarea>
      </label>
      <p id="cg-workspace-help" class="cg-workspace__help">The stored object must use <code>catalyst-grit-workspace/1.0</code> and <code>visibility: private</code>. Use the Python workspace export for complete project, revision, action-event, blocker, checkpoint, reassessment, review, and audit bundles.</p>
      <div class="cg-workspace__actions">
        <button type="button" data-cg-workspace-load>Load saved workspace</button>
        <button type="button" data-cg-workspace-save>Save private workspace</button>
        <button type="button" data-cg-workspace-clear>Delete saved workspace</button>
      </div>
      <p class="cg-workspace__boundary">Private by default. Do not use Catalyst Grit for diagnosis, employee ranking, automated eligibility, or hidden performance evaluation.</p>
    </section>
    <?php
    return ob_get_clean();
}
add_shortcode('catalyst_grit_workspace', 'catalyst_grit_workspace_shortcode');

function catalyst_grit_workspace_authorize() {
    if (!is_user_logged_in() || !current_user_can('read')) {
        wp_send_json_error(array('message' => 'Authentication and read access are required.'), 403);
    }
    check_ajax_referer('catalyst_grit_workspace_v140', 'nonce');
}

function catalyst_grit_workspace_load() {
    catalyst_grit_workspace_authorize();
    $value = get_user_meta(get_current_user_id(), '_catalyst_grit_workspace_v140', true);
    if (!is_array($value)) {
        $value = array(
            'format' => 'catalyst-grit-workspace/1.0',
            'product_version' => CATALYST_GRIT_DEMO_VERSION,
            'visibility' => 'private',
            'projects' => array(),
        );
    }
    wp_send_json_success(array('workspace' => $value));
}
add_action('wp_ajax_catalyst_grit_workspace_load', 'catalyst_grit_workspace_load');

function catalyst_grit_workspace_save() {
    catalyst_grit_workspace_authorize();
    $raw = isset($_POST['workspace']) ? wp_unslash($_POST['workspace']) : '';
    if (!is_string($raw) || strlen($raw) > 524288) {
        wp_send_json_error(array('message' => 'Workspace data is missing or exceeds 512 KB.'), 400);
    }
    $value = json_decode($raw, true);
    if (!is_array($value) || ($value['format'] ?? '') !== 'catalyst-grit-workspace/1.0') {
        wp_send_json_error(array('message' => 'Workspace format must be catalyst-grit-workspace/1.0.'), 400);
    }
    if (($value['visibility'] ?? 'private') !== 'private') {
        wp_send_json_error(array('message' => 'Workspace visibility must remain private.'), 400);
    }
    $value['visibility'] = 'private';
    $value['product_version'] = CATALYST_GRIT_DEMO_VERSION;
    $value['saved_at'] = gmdate('c');
    update_user_meta(get_current_user_id(), '_catalyst_grit_workspace_v140', $value);
    wp_send_json_success(array('message' => 'Private workspace saved.', 'saved_at' => $value['saved_at']));
}
add_action('wp_ajax_catalyst_grit_workspace_save', 'catalyst_grit_workspace_save');

function catalyst_grit_workspace_clear() {
    catalyst_grit_workspace_authorize();
    delete_user_meta(get_current_user_id(), '_catalyst_grit_workspace_v140');
    wp_send_json_success(array('message' => 'Saved workspace deleted.'));
}
add_action('wp_ajax_catalyst_grit_workspace_clear', 'catalyst_grit_workspace_clear');
