// The API stores times in UTC. pymongo returns them without an offset ("2026-10-26T19:00:00"), and the browser
// would read that as local time. Always parse API times with utc().
export const utc = (s) => (s ? new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z") : null);
