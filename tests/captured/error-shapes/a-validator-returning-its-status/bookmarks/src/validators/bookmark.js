const VALID_TAG_REGEX = /^[a-zA-Z0-9_-]*$/;

/**
 * Validates bookmark data according to the specification rules.
 * 
 * @param {object} params - The parameters object.
 * @param {string} params.title - The title string.
 * @param {string} params.url - The URL string.
 * @param {string|null|undefined} params.tag - The optional tag string.
 * @returns {{ valid: boolean, error?: { status: number, message: string } }}
 */
export function validateBookmark({ title, url, tag }) {
  // Validate Title: Required and non-empty after trimming
  if (title === undefined || title === null || typeof title !== 'string' || title.trim() === '') {
    return { valid: false, error: { status: 400, message: 'Title is required' } };
  }

  // Validate Title: Max length 500 characters
  if (title.length > 500) {
    return { valid: false, error: { status: 422, message: 'Title must not exceed 500 characters' } };
  }

  // Validate URL: Must start with http:// or https://
  if (typeof url !== 'string' || (!url.startsWith('http://') && !url.startsWith('https://'))) {
    return { valid: false, error: { status: 400, message: 'URL must start with http:// or https://' } };
  }

  // Validate Tag: If present, must match regex. If not present, it's valid (null/undefined).
  if (tag !== undefined && tag !== null) {
    if (typeof tag !== 'string' || !VALID_TAG_REGEX.test(tag)) {
      return { valid: false, error: { status: 400, message: 'Invalid tag format' } };
    }
  }

  return { valid: true };
}
