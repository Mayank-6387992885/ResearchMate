import { useEffect, useState } from "react";
import { UserRound } from "lucide-react";

import { API, apiFetch } from "../services/api";

export default function ProfilePhoto({
  imageVersion,
  previewUrl,
  name,
  className = "",
  fallbackClassName = "profile-avatar-fallback",
  fallbackText = "",
}) {
  const [loadedUrl, setLoadedUrl] = useState(null);
  const imageUrl = previewUrl || loadedUrl;

  useEffect(() => {
    let active = true;
    let objectUrl;
    setLoadedUrl(null);

    if (!imageVersion || previewUrl) {
      return () => {
        active = false;
      };
    }

    apiFetch(`${API.profileImage}?v=${encodeURIComponent(imageVersion)}`)
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("Could not load profile image.");
        }
        return response.blob();
      })
      .then((image) => {
        if (active) {
          objectUrl = URL.createObjectURL(image);
          setLoadedUrl(objectUrl);
        }
      })
      .catch(() => {
        if (active) setLoadedUrl(null);
      });

    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [imageVersion, previewUrl]);

  if (imageUrl) {
    return <img className={className} src={imageUrl} alt={`${name || "Profile"} profile`} />;
  }

  return (
    <span className={`${className} ${fallbackClassName}`} aria-label="No profile picture">
      {fallbackText || <UserRound size={28} />}
    </span>
  );
}
