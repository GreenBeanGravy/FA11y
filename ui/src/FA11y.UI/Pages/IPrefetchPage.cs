namespace FA11y.UI.Pages;

/// <summary>A page that loads its data before the user first opens it, and reloads when the account changes.</summary>
public interface IPrefetchPage
{
    /// <summary>The core is ready (or the account just settled): load the data if it isn't loaded.</summary>
    void Prefetch();

    /// <summary>Signed in or out: drop what was loaded and load again.</summary>
    void ResetData();
}
