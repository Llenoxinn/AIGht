using AIGht.Web.Models;

namespace AIGht.Web.Services;

public sealed class DemoData(List<SourcePage> pages)
{
    public List<SourcePage> Pages { get; } = pages;
    public Document Document => new() { Id = "doc_demo", Title = "Scholarship guidelines", PageCount = Pages.Count, InputType = "pdf", Coverage = Coverage() };
    private Coverage Coverage() => new() { ReadablePages = Pages.Select(page => page.PageNumber).ToList(), AnalyzedPages = Pages.Select(page => page.PageNumber).ToList() };
    public Citation Cite(int pageNumber, string quote)
    {
        var text = Pages[pageNumber - 1].Text;
        var start = text.IndexOf(quote, StringComparison.Ordinal);
        if (start < 0) throw new InvalidOperationException("Synthetic source fixture does not match its citation.");
        return new Citation { Id = $"demo_{pageNumber}_{start}", DocumentId = "doc_demo", PageNumber = pageNumber,
                              Start = Wire.CodePoints(text[..start]), End = Wire.CodePoints(text[..(start + quote.Length)]), Quote = quote };
    }
    public Analysis Explanation()
    {
        var gwa = Cite(2, Pages[1].Text.Split('\n', 2)[1]);
        var requirements = Cite(3, "Applicants must submit a certified transcript of records, proof of enrollment, a completed application form, and a copy of their school ID.");
        var deadline = Cite(4, Pages[3].Text.Split('\n', 2)[1]);
        Statement S(string text, Citation citation, string id = "", string kind = "") => new() { Text = text, CitationIds = [citation.Id], Id = id, Kind = kind };
        return new Analysis {
            Meaning = [new Statement { Text = "These sample guidelines describe the grade requirement, documents to prepare, and how the submission deadline is counted.", CitationIds = [gwa.Id, requirements.Id, deadline.Id] }],
            PossibleEffects = [S("Your GWA must be 2.00 or better under this example's grading convention. Other requirements still apply.", gwa)],
            Eligibility = [S("Maintain a GWA not exceeding 2.00.", gwa, "demo_eligibility")],
            Requirements = [S("Submit the four listed documents.", requirements, "demo_requirement")],
            Deadlines = [new Statement { Id = "demo_deadline", Text = "Within 15 calendar days after receiving the notice", Kind = "relative", Trigger = "receipt of notice", CountingRule = "fifteen calendar days", CitationIds = [deadline.Id] }],
            Actions = [S("Check your GWA against the 2.00 condition.", gwa, "demo_action_1", "suggested_step"),
                       S("Prepare your transcript, enrollment proof, application form, and school ID copy.", requirements, "demo_action_2", "document_requirement"),
                       S("Identify when you received the notice and confirm your submission deadline.", deadline, "demo_action_3", "suggested_step")],
            DetailsToCheck = [S("Calendar days include weekends and holidays unless another provision changes the rule. The exact due date depends on receipt of notice.", deadline)],
            NotStated = ["fees"], Citations = [gwa, requirements, deadline], Coverage = Coverage()
        };
    }
    public Answer Ask(string question)
    {
        var explanation = Explanation();
        var lower = question.ToLowerInvariant();
        string text, citation;
        if (lower.Contains("1.75")) { text = "A GWA of 1.75 meets the stated condition because it does not exceed 2.00. This does not establish overall eligibility."; citation = explanation.Citations[0].Id; }
        else if (lower.Contains("deadline") || lower.Contains("days")) { text = "The sample requires submission within 15 calendar days after receiving the notice. It does not provide your receipt date, so an exact due date cannot be established."; citation = explanation.Citations[2].Id; }
        else if (lower.Contains("submit") || lower.Contains("document")) { text = "Prepare a certified transcript, proof of enrollment, a completed application form, and a school ID copy."; citation = explanation.Citations[1].Id; }
        else return new Answer { Status = "insufficient_evidence", Statements = [new() { Text = "This guided example answers the grade, required-document, and deadline questions shown below. Connect configured AI processing to ask about your own document." }], Coverage = Coverage() };
        return new Answer { Statements = [new() { Text = text, CitationIds = [citation] }], Citations = explanation.Citations.Where(value => value.Id == citation).ToList(), Coverage = Coverage() };
    }
}
