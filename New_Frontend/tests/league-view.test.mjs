import assert from 'node:assert/strict';
import test from 'node:test';
import { canEnterLeague, cutoffCountdown, leagueNumber, leagueStateLabel, leagueStateMessage, pointsLabel, scoreLabel } from '../lib/league-view.ts';

test('missing metrics remain missing, while legitimate zero scores and points display as zero', () => {
  for (const missing of [null, undefined, '', '  ', 'not-a-number', Infinity, NaN]) {
    assert.equal(leagueNumber(missing), null);
    assert.equal(scoreLabel(missing), 'Awaiting score');
    assert.equal(pointsLabel(missing), '—');
  }
  assert.equal(scoreLabel(0), '0.00 / 100');
  assert.equal(scoreLabel('0.000000'), '0.00 / 100');
  assert.equal(pointsLabel('0'), '0');
});

test('weekly scores and league points have distinct units and display precision', () => {
  assert.equal(scoreLabel('87.456789'), '87.46 / 100');
  assert.equal(pointsLabel('25'), '25');
  assert.equal(scoreLabel('50'), '50.00 / 100');
  assert.equal(scoreLabel('100'), '100.00 / 100');
});

test('intake requires the authoritative server flag and a ready scheduled round', () => {
  const ready = { enabled: true, configuration_ready: true, can_submit: true, next_week: { id: 42 } };
  assert.equal(canEnterLeague(ready), true);
  assert.equal(canEnterLeague({ ...ready, enabled: false }), false);
  assert.equal(canEnterLeague({ ...ready, configuration_ready: false }), false);
  assert.equal(canEnterLeague({ ...ready, can_submit: false }), false);
  assert.equal(canEnterLeague({ ...ready, can_submit: undefined }), false);
  assert.equal(canEnterLeague({ ...ready, next_week: null }), false);
});

test('a browser countdown never extends the Friday scoring cutoff into Saturday', () => {
  const cutoff = '2026-10-03T00:00:00Z';
  assert.equal(cutoffCountdown(cutoff, Date.parse('2026-10-02T23:59:00Z')), '0h 1m until cutoff');
  assert.equal(cutoffCountdown(cutoff, Date.parse(cutoff)), 'Scoring window ended');
  assert.equal(cutoffCountdown(cutoff, Date.parse('2026-10-04T00:00:00Z')), 'Scoring window ended');
  assert.equal(cutoffCountdown(cutoff, Date.parse('2026-10-01T20:30:00Z')), '1d 3h 30m until cutoff');
  assert.equal(cutoffCountdown(null, Date.now()), null);
  assert.equal(cutoffCountdown('invalid', Date.now()), null);
});

test('pending data, exhibitions, frozen results and corrections are labeled explicitly', () => {
  assert.equal(leagueStateLabel('data_pending'), 'Data pending');
  assert.match(leagueStateMessage('data_pending'), /not counted as zero/);
  assert.match(leagueStateMessage('exhibition'), /no league points or official weekly winner/);
  assert.match(leagueStateMessage('finalizing'), /pending validation/);
  assert.match(leagueStateMessage('finalized'), /frozen/);
  assert.match(leagueStateMessage('corrected'), /recorded correction/);
  assert.match(leagueStateMessage('canceled'), /no league points/);
});
