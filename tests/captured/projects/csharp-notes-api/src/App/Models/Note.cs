namespace App.Models;

public record Note
{
    public int Id { get; init; }
    public string Title { get; init; } = "";
    public string Body { get; init; } = "";
}
