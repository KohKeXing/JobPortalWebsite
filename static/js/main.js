/**
 * Frontend Navigation Handler
 * Switches pages by navigating to Python Flask endpoints
 */
function switchView(viewId) {
    const viewRoutes = {
        'explore': '/seeker',     // Loads the protected seeker.html page
        'resumes': '/resumes',    // Loads resumes.html via Flask
        'dashboard': '/dashboard' // Loads dashboard.html via Flask
    };

    if (viewRoutes[viewId]) {
        window.location.href = viewRoutes[viewId];
    } else {
        console.error('Invalid view ID requested:', viewId);
    }
}