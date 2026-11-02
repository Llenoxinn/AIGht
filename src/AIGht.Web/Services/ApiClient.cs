using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using AIGht.Web.Models;

namespace AIGht.Web.Services;

public sealed class ApiClient(string baseUrl) : IDisposable
{
    private readonly HttpClient _http = new() { BaseAddress = new Uri(baseUrl.TrimEnd('/') + "/"), Timeout = TimeSpan.FromSeconds(60) };
    private readonly Dictionary<string, string> _pendingKeys = [];
    public Session? Session { get; private set; }
    public void Clear() { Session = null; _pendingKeys.Clear(); }
    private HttpRequestMessage Request(HttpMethod method, string path)
    {
        var request = new HttpRequestMessage(method, path);
        if (Session is not null) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", Session.SessionToken);
        return request;
    }
    private static async Task Check(HttpResponseMessage response, CancellationToken ct)
    {
        if (response.IsSuccessStatusCode) return;
        ErrorEnvelope? envelope = null;
        try { envelope = await response.Content.ReadFromJsonAsync<ErrorEnvelope>(Wire.Json, ct); } catch (JsonException) { }
        throw new InvalidOperationException(envelope?.Error.Message ?? "AIGht could not reach processing. Please try again.");
    }
    public async Task<Capabilities> Capabilities(CancellationToken ct) => await _http.GetFromJsonAsync<Capabilities>("api/v1/capabilities", Wire.Json, ct) ?? new();
    public async Task StartSession(string noticeVersion, CancellationToken ct)
    {
        if (Session is not null && Session.ExpiresAt > DateTimeOffset.UtcNow) return;
        using var response = await _http.PostAsJsonAsync("api/v1/sessions", new { processing_notice_version = noticeVersion, accept_processing = true }, ct);
        await Check(response, ct);
        Session = await response.Content.ReadFromJsonAsync<Session>(Wire.Json, ct) ?? throw new InvalidOperationException("The session could not be started.");
    }
    public async Task<T> Get<T>(string path, CancellationToken ct)
    {
        using var request = Request(HttpMethod.Get, path);
        using var response = await _http.SendAsync(request, ct);
        await Check(response, ct);
        return await response.Content.ReadFromJsonAsync<T>(Wire.Json, ct) ?? throw new InvalidOperationException("The server returned an empty response.");
    }
    private async Task<Acknowledgment> Submit(string path, string fingerprint, Func<HttpContent> content, CancellationToken ct)
    {
        var scope = path + ":" + fingerprint;
        if (!_pendingKeys.TryGetValue(scope, out var key)) _pendingKeys[scope] = key = Guid.NewGuid().ToString("N");
        for (var attempt = 0; ; attempt++)
        {
            try
            {
                using var request = Request(HttpMethod.Post, path);
                request.Headers.Add("Idempotency-Key", key);
                request.Content = content();
                using var response = await _http.SendAsync(request, ct);
                await Check(response, ct);
                var accepted = await response.Content.ReadFromJsonAsync<Acknowledgment>(Wire.Json, ct) ?? throw new InvalidOperationException("The request could not be accepted.");
                _pendingKeys.Remove(scope);
                return accepted;
            }
            catch (HttpRequestException) when (attempt == 0) { await Task.Delay(500, ct); }
        }
    }
    public Task<Acknowledgment> Paste(string title, string text, CancellationToken ct) => Submit("api/v1/documents/text", Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(title + "\n" + text))), () => JsonContent.Create(new { title, text }), ct);
    public Task<Acknowledgment> Upload(string filename, byte[] bytes, CancellationToken ct) => Submit("api/v1/documents", Convert.ToHexString(SHA256.HashData(bytes)) + filename, () =>
    {
        var form = new MultipartFormDataContent();
        var file = new ByteArrayContent(bytes);
        file.Headers.ContentType = new MediaTypeHeaderValue("application/pdf");
        form.Add(file, "file", filename);
        return form;
    }, ct);
    public Task<Acknowledgment> Analyze(string docid, CancellationToken ct) => Submit($"api/v1/documents/{docid}/analyses", "en", () => JsonContent.Create(new { language = "en" }), ct);
    public Task<Acknowledgment> Ask(string docid, string question, CancellationToken ct) => Submit($"api/v1/documents/{docid}/questions", question, () => JsonContent.Create(new { question, language = "en" }), ct);
    public async Task<Operation> Poll(Acknowledgment accepted, Action<string> progress, CancellationToken ct)
    {
        var delay = 1_000;
        while (true)
        {
            var operation = await Get<Operation>($"api/v1/operations/{accepted.OperationId}", ct);
            progress(operation.Stage);
            if (operation.State == "succeeded") return operation;
            if (operation.State is "failed" or "cancelled") throw new InvalidOperationException(operation.Error?.Message ?? "Processing was cancelled.");
            if (Session is null || Session.ExpiresAt <= DateTimeOffset.UtcNow) throw new InvalidOperationException("This temporary session has expired.");
            await Task.Delay(delay, ct);
            delay = Math.Min(10_000, delay + 1_000);
        }
    }
    public async Task<byte[]> Source(string docid, CancellationToken ct)
    {
        using var request = Request(HttpMethod.Get, $"api/v1/documents/{docid}/source");
        using var response = await _http.SendAsync(request, ct);
        await Check(response, ct);
        return await response.Content.ReadAsByteArrayAsync(ct);
    }
    public async Task Delete(string docid, CancellationToken ct)
    {
        using var request = Request(HttpMethod.Delete, $"api/v1/documents/{docid}");
        using var response = await _http.SendAsync(request, ct);
        await Check(response, ct);
    }
    public async Task EndSession(CancellationToken ct)
    {
        using var request = Request(HttpMethod.Delete, "api/v1/sessions/current");
        using var response = await _http.SendAsync(request, ct);
        await Check(response, ct);
        Clear();
    }
    public void Dispose() { Clear(); _http.Dispose(); }
}
