// A support ticket, described once. No JSON Schema, no Pydantic model by hand.
enum Priority {
  Low
  Medium
  High
}

class Ticket {
  summary   string
  priority  Priority
  effort_days int
  tags      string[]
}

// The function's return type is what BAML's parser aligns against.
// The client is only used when you actually CALL the model; b.parse never does.
function TriageTicket(report: string) -> Ticket {
  client "openai-responses/gpt-5-mini"
  prompt #"
    Triage this report into a ticket.
    {{ report }}
    {{ ctx.output_format }}
  "#
}
