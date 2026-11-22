/** 请求层：GET 读取 / 错误归一 / 失败实时日志。 */

import { BASE_URL, REQUEST_TIMEOUT_MS } from '../config'
import { logger } from './logger'

export class ApiError extends Error {
  statusCode: number

  constructor(statusCode: number, message: string) {
    super(message)
    this.statusCode = statusCode
  }
}

/** 记录最终呈给用户的请求失败：statusCode=0 为网络层失败，其余为服务端已响应。 */
function logApiFailure(path: string, e: unknown): void {
  const statusCode = e instanceof ApiError ? e.statusCode : 0
  const message = e instanceof Error ? e.message : String(e)
  if (statusCode === 0) {
    logger.error('GET', path, message)
  } else {
    logger.warn('GET', path, statusCode, message)
  }
}

async function requestGet<T>(path: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    wx.request({
      url: BASE_URL + path,
      method: 'GET',
      timeout: REQUEST_TIMEOUT_MS,
      success: (res) => {
        if (res.statusCode >= 400) {
          const detail =
            (res.data as { detail?: string } | undefined)?.detail ?? `HTTP ${res.statusCode}`
          reject(new ApiError(res.statusCode, detail))
          return
        }
        resolve(res.data as T)
      },
      fail: (err) => reject(new ApiError(0, err.errMsg ?? '网络异常')),
    })
  })
}

export const http = {
  get: requestGet,
}
