/**
 * useFirestore — Firestore real-time subscription helpers.
 */

import { useEffect, useState } from 'react';
import { collection, onSnapshot, doc, addDoc, updateDoc, deleteDoc } from 'firebase/firestore';
import { db } from '@/lib/firebase';

export function useFirestore(collectionName) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!collectionName) return;
    setLoading(true);
    const ref = collection(db, collectionName);
    const unsub = onSnapshot(
      ref,
      (snapshot) => {
        setData(snapshot.docs.map((d) => ({ id: d.id, ...d.data() })));
        setLoading(false);
      },
      (err) => {
        setError(err);
        setLoading(false);
      },
    );
    return unsub;
  }, [collectionName]);

  const add = (item) => addDoc(collection(db, collectionName), item);
  const update = (id, fields) => updateDoc(doc(db, collectionName, id), fields);
  const remove = (id) => deleteDoc(doc(db, collectionName, id));

  return { data, loading, error, add, update, remove };
}
