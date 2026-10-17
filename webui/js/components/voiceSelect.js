// The voice picker. data-voices lets services/voices.js refill it once the full list arrives.
import { voiceOptions } from '../services/voices.js';

export function voiceSelect(id, selected) {
  return '<select id="' + id + '" class="input" data-voices>' + voiceOptions(selected) + '</select>';
}
