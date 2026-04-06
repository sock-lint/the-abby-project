import { motion } from 'framer-motion';
import { Image } from 'lucide-react';
import { getPortfolio } from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';

export default function Portfolio() {
  const { data, loading } = useApi(getPortfolio);

  if (loading) return <Loader />;
  const groups = data || [];

  return (
    <div className="space-y-6">
      <h1 className="font-heading text-2xl font-bold">Portfolio</h1>

      {groups.length === 0 ? (
        <Card className="text-center py-12 text-forge-text-dim">
          <Image className="mx-auto mb-3" size={32} />
          <div>No photos yet. Upload progress photos from your projects!</div>
        </Card>
      ) : (
        groups.map((group) => (
          <div key={group.project_id}>
            <h2 className="font-heading text-lg font-bold mb-3">{group.project_title}</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {group.photos.map((photo, i) => (
                <motion.div
                  key={photo.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="group cursor-pointer"
                >
                  <div className="relative aspect-square rounded-xl overflow-hidden bg-forge-card border border-forge-border">
                    <img
                      src={photo.image}
                      alt={photo.caption}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    />
                    {photo.caption && (
                      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-2">
                        <div className="text-xs text-white truncate">{photo.caption}</div>
                      </div>
                    )}
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
