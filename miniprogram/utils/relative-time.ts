/** 「更新于」时间档位（产品定稿）：
 * <1 分钟「刚刚」；1-29 分钟「N分钟前」；30-59 分钟「半小时前」；
 * 同日更早「今天 HH:mm」；昨天「昨天 HH:mm」；更早「MM-DD HH:mm」。
 * 时长档优先于日历档（跨零点不久的数据仍显示时长）。
 */

export function formatUpdatedAt(d: Date, now = new Date()): string {
  const minutes = Math.floor((now.getTime() - d.getTime()) / 60000)
  if (minutes < 1) return '刚刚'

  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  const isYesterday =
    d.getFullYear() === yesterday.getFullYear() &&
    d.getMonth() === yesterday.getMonth() &&
    d.getDate() === yesterday.getDate()

  const hhmm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  if (minutes < 30) return `${minutes}分钟前`
  if (minutes < 60) return '半小时前'
  if (sameDay) return `今天 ${hhmm}`
  if (isYesterday) return `昨天 ${hhmm}`
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${hhmm}`
}
