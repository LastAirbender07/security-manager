
/**
 * Validates if the given string is a valid GitHub repository URL.
 * 
 * Accepted formats:
 * - https://github.com/username/repo
 * - https://github.com/username/repo/
 * 
 * @param url The URL string to validate
 * @returns true if the URL is a valid GitHub repository URL, false otherwise
 */
export const isValidGithubUrl = (url: string): boolean => {
    // Basic regex for GitHub repository URL
    // Checks for https://github.com/{owner}/{repo}
    // Owner and repo names can contain alphanumeric characters, hyphens, underscores, and periods.
    const githubUrlRegex = /^https:\/\/github\.com\/[a-zA-Z0-9-]+\/[a-zA-Z0-9-._]+(\/)?$/;
    return githubUrlRegex.test(url);
};
