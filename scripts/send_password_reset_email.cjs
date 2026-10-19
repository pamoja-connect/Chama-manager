const { ReplitConnectors } = require("@replit/connectors-sdk");

async function main() {
  let input = "";
  for await (const chunk of process.stdin) {
    input += chunk;
    if (input.length > 100000) {
      throw new Error("Email request too large");
    }
  }

  const message = JSON.parse(input);
  const connectors = new ReplitConnectors();
  const response = await connectors.proxy("resend", "/emails", {
    method: "POST",
    body: message,
  });

  if (!response.ok) {
    console.error(`RESEND_HTTP_${response.status}`);
    process.exitCode = 1;
  }
}

main().catch(() => {
  console.error("RESEND_SEND_FAILED");
  process.exitCode = 1;
});
