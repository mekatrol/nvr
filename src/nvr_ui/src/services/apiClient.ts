export class ApiError extends Error {
  constructor(
    message: string,
    readonly path: string,
    readonly status?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export const getJson = async <T>(path: string): Promise<T> => {
  return requestJson<T>(path, { method: 'GET' })
}

export const postJson = async <T>(path: string, body: Record<string, unknown>): Promise<T> => {
  return requestJson<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export const postForm = async <T>(path: string, body: FormData): Promise<T> => {
  return requestJson<T>(path, {
    method: 'POST',
    body,
  })
}

const requestJson = async <T>(path: string, init: RequestInit): Promise<T> => {
  let response: Response
  try {
    response = await fetch(`${__API_BASE_URL__}${path}`, init)
  } catch {
    throw new ApiError(`Unable to reach NVR web API at ${path}`, path, undefined)
  }

  if (!response.ok) {
    throw new ApiError(await responseErrorMessage(response), path, response.status)
  }

  return response.json() as Promise<T>
}

const responseErrorMessage = async (response: Response): Promise<string> => {
  try {
    const payload = (await response.clone().json()) as { error?: unknown }
    if (typeof payload.error === 'string' && payload.error.length > 0) {
      return payload.error
    }
  } catch {
    return `${response.status} ${response.statusText}`
  }
  return `${response.status} ${response.statusText}`
}
