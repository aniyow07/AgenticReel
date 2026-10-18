// The voice picker with a play button that speaks a short sample of the chosen voice at the chosen speed.
// data-voices lets services/voices.js refill the list once it arrives.
import { icon } from '../core/icons.js';
import { voiceOptions } from '../services/voices.js';

export function voiceSelect(id, selected) {
  return '<div class="voice-row"><select id="' + id + '" class="input" data-voices>' + voiceOptions(selected) + '</select>' +
    '<button type="button" class="icon-btn voice-play" data-voice-play="' + id + '" aria-label="Play a sample of this voice" title="Hear this voice">' +
    icon.play + '</button></div>';
}
