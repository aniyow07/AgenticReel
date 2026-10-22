// The voice picker: a Natural / Classic engine switch, then the voice list with a play button that speaks a
// short sample of the chosen voice at the chosen speed.
// data-voices lets services/voices.js refill the list once it arrives; data-engine says whose voices it holds.
import { esc } from '../core/dom.js';
import { icon } from '../core/icons.js';
import { segmented } from './segmented.js';
import { ENGINES, voiceOptions } from '../services/voices.js';

export function voiceSelect(id, selected, engine) {
  return '<div class="voice-row"><select id="' + id + '" class="input" data-voices data-engine="' + esc(engine) + '">' +
    voiceOptions(selected, engine) + '</select>' +
    '<button type="button" class="icon-btn voice-play" data-voice-play="' + id + '" aria-label="Play a sample of this voice" title="Hear this voice">' +
    icon.play + '</button></div>';
}

// The engine switch for the picker with this id; Classic voices need an internet connection.
export function engineSwitch(id, engine) {
  return '<div data-engine-for="' + id + '" title="Natural: realistic voices made on this computer. Classic: Microsoft voices, needs internet.">' +
    segmented('Voice engine', ENGINES, engine) + '</div>';
}

// The engine currently chosen in a switch.
export function engineOf(id) {
  const b = document.querySelector('[data-engine-for="' + id + '"] button[aria-pressed="true"]');
  return b ? b.dataset.val : '';
}
