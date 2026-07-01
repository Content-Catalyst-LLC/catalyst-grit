<?php
/**
 * Plugin Name: Catalyst Grit Demo
 * Description: Browser-based Sustainable Catalyst demo for creating a Catalyst Grit recovery record. Provides shortcode [catalyst_grit_demo].
 * Version: 1.0.0
 * Author: Content Catalyst LLC
 * License: MIT
 */

if (!defined('ABSPATH')) { exit; }

function catalyst_grit_demo_assets() {
    $base = plugin_dir_url(__FILE__);
    wp_enqueue_style('catalyst-grit-demo', $base . 'assets/catalyst-grit-demo.css', array(), '1.0.0');
    wp_enqueue_script('catalyst-grit-demo', $base . 'assets/catalyst-grit-demo.js', array(), '1.0.0', true);
}
add_action('wp_enqueue_scripts', 'catalyst_grit_demo_assets');

function catalyst_grit_demo_shortcode() {
    ob_start();
    ?>
    <section class="cg-demo" aria-labelledby="cg-demo-title">
      <div class="cg-demo__header">
        <p class="cg-demo__eyebrow">Catalyst Grit Demo</p>
        <h3 id="cg-demo-title">Build a Recovery Record</h3>
        <p>Describe a setback, name the recovery conditions, and generate a reviewable record with a score, flags, next actions, decision note, and JSON export. This educational demo runs in the browser.</p>
      </div>
      <div class="cg-demo__grid">
        <form class="cg-demo__form" data-cg-form>
          <label><span>Challenge or setback</span><textarea name="challenge" rows="4">A project lost momentum after conflicting feedback and a missed checkpoint.</textarea></label>
          <div class="cg-demo__two">
            <label><span>Domain</span><select name="domain"><option value="project">Project</option><option value="career">Career</option><option value="learning">Learning</option><option value="work">Work</option><option value="relationship">Relationship</option><option value="health_wellbeing">Health / wellbeing</option><option value="other">Other</option></select></label>
            <label><span>Review status</span><select name="review_status"><option value="draft">Draft</option><option value="needs_review">Needs review</option><option value="reviewed">Reviewed</option></select></label>
          </div>
          <div class="cg-demo__sliders">
            <label><span>Impact severity <strong data-out="impact_severity">7</strong>/10</span><input type="range" name="impact_severity" min="1" max="10" value="7"></label>
            <label><span>Pressure level <strong data-out="pressure_level">8</strong>/10</span><input type="range" name="pressure_level" min="1" max="10" value="8"></label>
            <label><span>Energy level <strong data-out="energy_level">5</strong>/10</span><input type="range" name="energy_level" min="1" max="10" value="5"></label>
            <label><span>Support level <strong data-out="support_level">6</strong>/10</span><input type="range" name="support_level" min="1" max="10" value="6"></label>
            <label><span>Clarity level <strong data-out="clarity_level">4</strong>/10</span><input type="range" name="clarity_level" min="1" max="10" value="4"></label>
          </div>
          <label><span>Recovery actions, one per line</span><textarea name="recovery_actions" rows="5">Clarify the next decision owner
Break the work into a 48-hour recovery task
Document unresolved assumptions
Schedule a short review</textarea></label>
          <label><span>Time horizon in days</span><input type="number" name="time_horizon_days" min="1" value="14"></label>
          <div class="cg-demo__actions"><button type="button" data-cg-generate>Generate record</button><button type="button" data-cg-download>Download JSON</button></div>
        </form>
        <div class="cg-demo__output" aria-live="polite">
          <div class="cg-demo__score"><span>Recovery score</span><strong data-cg-score>—</strong></div>
          <div class="cg-demo__panel"><h4>Resilience state</h4><p data-cg-state>Generate a record to view the recovery state.</p></div>
          <div class="cg-demo__panel"><h4>Review flags</h4><ul data-cg-flags><li>No flags generated yet.</li></ul></div>
          <div class="cg-demo__panel"><h4>Next actions</h4><ul data-cg-actions><li>No actions generated yet.</li></ul></div>
          <div class="cg-demo__panel"><h4>Decision note</h4><p data-cg-note>Use the form to generate a structured recovery note.</p></div>
          <details class="cg-demo__json"><summary>JSON export</summary><pre data-cg-json>{}</pre></details>
        </div>
      </div>
      <p class="cg-demo__disclaimer">Educational demo only. Not mental-health advice, diagnosis, HR evaluation, professional coaching, or a guarantee of outcomes. Inputs stay in the browser unless you choose to export them.</p>
    </section>
    <?php
    return ob_get_clean();
}
add_shortcode('catalyst_grit_demo', 'catalyst_grit_demo_shortcode');
