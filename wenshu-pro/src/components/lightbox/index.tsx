import ReactLightbox, { type LightboxExternalProps } from 'yet-another-react-lightbox';
import Download from 'yet-another-react-lightbox/plugins/download';
import Zoom from 'yet-another-react-lightbox/plugins/zoom';
import 'yet-another-react-lightbox/styles.css';

type Props = LightboxExternalProps & { disableVideo?: boolean; disableThumbnails?: boolean; enableDownload?: boolean };
export function Lightbox({ disableVideo: _video, disableThumbnails: _thumbnails, enableDownload = false, ...props }: Props) {
  return <ReactLightbox {...props} plugins={enableDownload ? [Zoom, Download] : [Zoom]} />;
}
