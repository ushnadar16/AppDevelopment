// Plain-language explanations for server error codes (never show raw codes alone).
const M = {
  NETWORK: 'Cannot reach the server. Check your connection or the server address in Account.',
  UNAUTHENTICATED: 'Your session has expired or the password is wrong. Please sign in again.',
  FORBIDDEN: "Your role doesn't allow this action.",
  RATE_LIMITED: 'Too many requests. Please wait a few seconds and try again.',
  VALIDATION_ERROR: 'Some details are missing or invalid. Please check the form.',
  OUT_OF_STOCK: 'Sorry, this item just sold out.',
  PAYMENT_DECLINED: 'Your card was declined. No money was taken.',
  PAYMENT_CAPTURE_FAILED: "The payment couldn't be completed. No money was taken.",
  INVALID_DISCOUNT_CODE: "That discount code isn't valid.",
  MATCH_NOT_IN_PROGRESS: 'This match is not in progress, so scores cannot be added.',
  ILLEGAL_TRANSITION: "The match can't move to that status from where it is now.",
  TIE_NOT_ALLOWED: 'Scores are level and this sport needs a winner. Record a tie-break winner first.',
  INVALID_COMPENSATION: 'That event was already corrected or cannot be undone.',
  INNINGS_COMPLETE: "This team's innings is already complete.",
  SERIES_ALREADY_DECIDED: 'The series is already decided.',
  UNKNOWN_EVENT_TYPE: "This scoring action doesn't exist for this sport.",
  TRANSFER_WINDOW_CLOSED: 'The transfer window is closed on that date.',
  SQUAD_FULL: 'The destination squad is already full.',
  NOT_IN_SQUAD: 'The player is no longer in that squad (someone changed it first).',
  PLAYER_ON_LOAN: 'The player is on loan and cannot be moved until the loan ends.',
  MIN_POSITION_VIOLATION: 'This would leave the squad without enough players in that position.',
  CROSS_TENANT_TRANSFER: 'Players can only move between squads of the same organisation.',
  INVALID_BASE_VERSION: 'Your device had out-of-date data. The server version was kept.',
  DUPLICATE_EVENT_ID: 'This action was already recorded.',
  MATCH_NOT_FOUND: 'This match no longer exists.',
  PLAYER_NOT_FOUND: 'This player no longer exists.',
  SQUAD_NOT_FOUND: 'That squad no longer exists.',
};

export function explain(code, fallback) {
  return M[code] || fallback || 'Something went wrong. Please try again.';
}

export function errorText(e) {
  return explain(e && e.code, e && e.message);
}
