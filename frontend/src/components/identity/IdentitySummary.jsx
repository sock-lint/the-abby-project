import IdentityPortrait from './IdentityPortrait';
import IdentityChips from './IdentityChips';

/** The same saved identity at navigation, menu and profile sizes. */
export default function IdentitySummary({
  name, avatar, frame, title, badge, level, details, portraitSize = 'sm',
  imageAlt = '', portraitClassName = '', nameAs: Name = 'span', as: Container = 'span',
  showRecognition = true, className = '',
}) {
  const Row = Container === 'span' ? 'span' : 'div';
  return <Container className={`identity-summary ${className}`} data-identity-summary="true">
    <Row className="identity-summary__heading">
      <IdentityPortrait name={name} avatar={avatar} frame={frame} size={portraitSize}
        imageAlt={imageAlt} level={level} className={portraitClassName} />
      <Row className="identity-summary__copy">
        <Name className="identity-summary__name">{name}</Name>
        {details && <span className="identity-summary__details">{details}</span>}
      </Row>
    </Row>
    {showRecognition && <IdentityChips title={title} badge={badge} />}
  </Container>;
}
