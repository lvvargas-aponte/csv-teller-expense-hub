import React from 'react';

export default function Spin({ large }) {
  return <span className={`spinner${large ? ' spinner--large' : ''}`} />;
}
