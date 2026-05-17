/**
 * OpenAPI 类型定义(自动生成,不要手改)
 *
 * 生成命令:
 *   pnpm gen:api
 *   # 等价于
 *   openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts
 *
 * 前置条件:后端已起来在 http://localhost:8000(uvicorn)。
 *
 * TODO(接手者):后端 8000 起来后跑一次 `pnpm gen:api`,本文件会被自动覆盖为完整 paths/components/operations 三大命名空间。
 *               届时 src/api/client.ts 中 createClient<any> 也要改为 createClient<paths>。
 */

// 占位 export,避免 import 'paths' / 'components' 立即报错;
// 真正生成后这里会被 openapi-typescript 整个覆盖。
export interface paths {}
export interface components {}
export interface operations {}
export interface webhooks {}
