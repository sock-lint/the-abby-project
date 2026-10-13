// Raw Playwright errors, locator calls and attachments can contain credentials
// or private server responses. The suite persists its own allowlisted result.
export default class QuietReporter {
  printsToStdio() { return false; }
}
