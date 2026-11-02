using System.Text;
using System.Text.Json;

namespace AIGht.Web.Models;

public static class Wire
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
    public static int Utf16Index(string value, int codePoints)
    {
        var result = 0;
        foreach (var rune in value.EnumerateRunes()) { if (codePoints-- <= 0) break; result += rune.Utf16SequenceLength; }
        return result;
    }
    public static int CodePoints(string value) => value.EnumerateRunes().Count();
}

public sealed class Capabilities
{
    public bool ProcessingAvailable { get; set; }
    public Dictionary<string, bool> Features { get; set; } = [];
    public Notice? ProcessingNotice { get; set; }
    public List<Processor> Processors { get; set; } = [];
}
public sealed class Notice { public string Version { get; set; } = ""; public string Url { get; set; } = ""; }
public sealed class Processor { public string Name { get; set; } = ""; public string RetentionSummary { get; set; } = ""; public string Region { get; set; } = ""; }
public sealed class Session { public string SessionId { get; set; } = ""; public string SessionToken { get; set; } = ""; public DateTimeOffset ExpiresAt { get; set; } }
public sealed class Acknowledgment { public string DocumentId { get; set; } = ""; public string OperationId { get; set; } = ""; }
public sealed class Coverage
{
    public string Status { get; set; } = "complete";
    public List<int> ReadablePages { get; set; } = [];
    public List<int> PartialPages { get; set; } = [];
    public List<int> UnreadablePages { get; set; } = [];
    public List<int> AnalyzedPages { get; set; } = [];
    public List<string> Reasons { get; set; } = [];
}
public sealed class SourceWarning { public string Code { get; set; } = ""; public string Message { get; set; } = ""; public List<int> PageNumbers { get; set; } = []; }
public sealed class Document
{
    public string Id { get; set; } = "";
    public string Title { get; set; } = "";
    public string InputType { get; set; } = "pdf";
    public string Status { get; set; } = "ready";
    public int PageCount { get; set; }
    public Coverage? Coverage { get; set; }
    public List<SourceWarning> Warnings { get; set; } = [];
    public DateTimeOffset ExpiresAt { get; set; }
}
public sealed class SourcePage
{
    public int PageNumber { get; set; }
    public string Status { get; set; } = "readable";
    public string Text { get; set; } = "";
    public List<SourceWarning> Warnings { get; set; } = [];
}
public sealed class Citation
{
    public string Id { get; set; } = "";
    public string DocumentId { get; set; } = "";
    public int PageNumber { get; set; }
    public int Start { get; set; }
    public int End { get; set; }
    public string Quote { get; set; } = "";
    public List<double[]> Boxes { get; set; } = [];
}
public sealed class Statement
{
    public string Text { get; set; } = "";
    public List<string> CitationIds { get; set; } = [];
    public string Id { get; set; } = "";
    public string Kind { get; set; } = "";
    public string? Date { get; set; }
    public string? Trigger { get; set; }
    public string? CountingRule { get; set; }
}
public sealed class Analysis
{
    public List<Statement> Meaning { get; set; } = [];
    public List<Statement> PossibleEffects { get; set; } = [];
    public List<Statement> Requirements { get; set; } = [];
    public List<Statement> Eligibility { get; set; } = [];
    public List<Statement> Fees { get; set; } = [];
    public List<Statement> Deadlines { get; set; } = [];
    public List<Statement> Actions { get; set; } = [];
    public List<Statement> DetailsToCheck { get; set; } = [];
    public List<string> NotStated { get; set; } = [];
    public List<Citation> Citations { get; set; } = [];
    public Coverage Coverage { get; set; } = new();
    public List<SourceWarning> Warnings { get; set; } = [];
}
public sealed class Answer
{
    public string Status { get; set; } = "answered";
    public List<Statement> Statements { get; set; } = [];
    public List<Citation> Citations { get; set; } = [];
    public Coverage Coverage { get; set; } = new();
    public List<SourceWarning> Warnings { get; set; } = [];
}
public sealed class Operation
{
    public string State { get; set; } = "queued";
    public string Stage { get; set; } = "queued";
    public JsonElement? Result { get; set; }
    public ErrorBody? Error { get; set; }
}
public sealed class ErrorBody { public string Code { get; set; } = ""; public string Message { get; set; } = ""; public string RequestId { get; set; } = ""; }
public sealed class ErrorEnvelope { public ErrorBody Error { get; set; } = new(); }
public sealed class DemoFixture { public List<SourcePage> Pages { get; set; } = []; }
