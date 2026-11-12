// Error code -> what we say (docs/13 section 6). Show the server's message for known codes.
const COPY = {
  BAD_CREDENTIALS: "Wrong e-mail or password.",
  EMAIL_NOT_VERIFIED: "Check your inbox and confirm your e-mail first.",
  ACCOUNT_DISABLED: "This account is turned off. Contact support.",
  LOCKED: "Too many attempts. Try again later.",
  RATE_LIMITED: "Too many requests. Try again shortly.",
  BAD_CODE: "That code is not right.",
  CHALLENGE_EXPIRED: "Sign in again.",
  TOKEN_INVALID: "This link is not valid any more. Ask for a new one.",
  PASSWORD_TOO_SHORT: "Use at least 10 characters.",
  TOO_COMMON: "That password is too easy to guess.",
  BAD_EMAIL: "Enter a valid e-mail address.",
  SIGNUP_CLOSED: "Sign-up is closed right now.",
  BAD_ORIGIN: "Reload the page and try again.",
  TOO_LARGE: "That request is too large.",
  UPGRADE_REQUIRED: "That is part of Pro. See plans.",
  LIMIT_REACHED: "You have reached your plan's limit. Remove one or see plans.",
  SIGN_IN_REQUIRED: "Sign in to continue.",
};

export function sayError(err) {
  if (!err) return "";
  // UNREADABLE_ERROR carries its own sentence (api.js): the reply could not be parsed, which is a
  // different fact from our server reporting a fault, and saying the wrong one sent us looking in
  // the wrong place for a day.
  if (err.code === "UNREADABLE_ERROR") {
    return (err.message || "The server's reply could not be read.") + (err.requestId ? ` Reference: ${err.requestId}` : "");
  }
  if (err.code === "SERVER_ERROR" || !err.code) {
    return "Something went wrong on our side." + (err.requestId ? ` Reference: ${err.requestId}` : "");
  }
  return err.message || COPY[err.code] || "Something went wrong.";
}
