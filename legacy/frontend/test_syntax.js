const fs = require('fs');
const acorn = require('acorn');
const html = fs.readFileSync('/Users/jaydenyu/Projects/kol-monitor/frontend/index.html', 'utf8');

// Extract all <script> tags
const regex = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
let match;
while ((match = regex.exec(html)) !== null) {
  const code = match[1];
  try {
    acorn.parse(code, { ecmaVersion: 2022, sourceType: 'script' });
    console.log("Script block OK");
  } catch (e) {
    console.log("Syntax error inside a script block at index/line", e);
  }
}
