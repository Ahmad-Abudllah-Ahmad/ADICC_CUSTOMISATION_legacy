// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Offline slice for the field PWA (TOP-30 #14).
 *
 * Public surface:
 *   - connectivity        online/offline detection (framework-light store)
 *   - mutationQueue       storage-agnostic, idempotent, ordered replay queue
 *   - fieldQueue          the concrete field queue + HTTP sender wiring
 *   - registerFieldSW     scoped service-worker registration helper
 */

export {
  isOnline,
  subscribeConnectivity,
  emitConnectivityForTests,
  type ConnectivityListener,
} from './connectivity';

export {
  MutationQueue,
  sortByFifo,
  newClientOpId,
  createMemoryQueueStorage,
  createIndexedDbQueueStorage,
  type QueuedOp,
  type QueueStorage,
  type OpSender,
  type ReplayOutcome,
  type DrainResult,
  type DrainSummary,
  type EnqueueInput,
  type HttpMethod,
  type MutationQueueOptions,
} from './mutationQueue';

export {
  getFieldQueue,
  createFieldSender,
  pickQueueStorage,
  resetFieldQueueForTests,
  type FieldHeadersProvider,
} from './fieldQueue';

export {
  registerFieldServiceWorker,
  unregisterFieldServiceWorker,
  type RegisterFieldSWResult,
} from './registerFieldSW';
