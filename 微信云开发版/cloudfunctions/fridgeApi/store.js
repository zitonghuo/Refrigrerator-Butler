'use strict';
// All client collection permissions must be read:false/write:false.
// Only this server-side adapter reads the collections.
exports.createStore = db => ({
  transaction: run => db.runTransaction(async transaction => run({
    async get(collection, id) {
      const result = await transaction.collection(collection).doc(id).get();
      // CloudBase transactions return data:null for missing documents.
      return result.data || null;
    },
    async put(collection, id, value) {
      const data = { ...value }; delete data._id;
      await transaction.collection(collection).doc(id).set({ data });
    },
    async remove(collection, id) { await transaction.collection(collection).doc(id).remove(); }
  }))
});
